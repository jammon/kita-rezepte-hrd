# coding: utf-8
import cgi
import os
import logging
from datetime import date, timedelta

from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

import jinja2

import models
import tools
from auth import AuthorizedRequestHandler, isauthorized

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

REZEPTKATEGORIEN = (u"Reis",  u"Teigwaren", u"Getreide", u"Kartoffeln",
                    u"Gemüse", u"Suppe", u"Fischgericht", u"Lieblingsgericht")
REZEPTKATEGORIEN_KURZ = (u"Reis",  u"Teigw.", u"Getr.", u"Kart.", u"Gemüse",
                         u"Suppe", u"Fisch", u"Liebl.")
GAENGE = (u'Vorspeise', u'Hauptgang', u'Nachtisch')

loginurl = users.create_login_url("/")
logouturl = users.create_logout_url("/")

class NotFoundError(Exception):
    """Ein Objekt wurde nicht in der Datenbank gefunden.

    Attributes:
        msg  -- explanation of the error
    """

    def __init__(self, msg):
        self.msg = msg

def standard_template_values():
    """Gibt alle Informationen, die auf jeder Seite benötigt werden.

    'logintext': 'Abmelden' oder 'Anmelden',
    'loginurl': URL zum ein- oder ausloggen,
    'isadmin': ...,
    'isauthorized': ...
    """
    if isauthorized():
        res = {'logintext': 'Abmelden',
            'loginurl': logouturl,
            'isadmin': users.is_current_user_admin(),
            'isauthorized': True,
        }
    else:
        res = {'logintext': 'Anmelden',
            'loginurl': loginurl,
            'isadmin': False,
        }
    user = users.get_current_user()
    if user:
        res['username'] = user.nickname()
    return res

def getRezept(rezept_id, version=1):
    """Liefert aus der Datenbank ein Rezept und die Anzahl der vorhandenen
    Versionen

    Parameter:
    id des Rezepts - obligat,
    version - Default ist 1
    """
    try:
        version = int(version)
    except ValueError:
        raise NotFoundError(u"Rezept %s mit Version %s nicht gefunden." % (rezept_id, version))
    rezepte = models.Rezept.all().filter("id =",rezept_id).filter('version =', version)
    rezept = rezepte.get()
    if rezept is None:
        raise NotFoundError(u"Rezept %s nicht gefunden." % rezept_id)
    return (rezept,
            models.Rezept.all(keys_only=True).filter("id =",rezept_id).count())

class TemplateWriter(object):
    def write_out_template(self, template_name, values):
        template = JINJA_ENVIRONMENT.get_template(template_name)
        self.response.write(template.render(values))

class MainPage(webapp.RequestHandler, TemplateWriter):
    def get(self):
        self.write_out_template('index.html', standard_template_values())


class ZutatenEingabe(AuthorizedRequestHandler, TemplateWriter):
    def post(self, *param):
        if len(param)>0:
            zutat = db.get(db.Key(param[0]))
        else:
            zutat = models.Zutat()
        zutat.name = self.request.get('name')
        zutat.einheit = self.request.get('einheit')
        preis = self.request.get('preis')
        if preis:
            preis = preis.replace(',', '.')
            zutat.preis_pro_einheit = int(round(100*float(preis)))
        # TODO: Fehlerbehandlung für Fehleingaben
        menge = self.request.get('menge')
        if menge:
            zutat.menge_pro_einheit = int(menge)
            zutat.masseinheit = self.request.get('masseinheit')
        zutat.kategorie = self.request.get('kategorie')

        zutat.put()
        if len(param)>0:
            zutat.updateRezeptpreise()
        self.redirect('/zutaten')

    def get(self, *param):
        template_values = standard_template_values()
        template_values.update({
          'masseinheiten': models.MASSEINHEITEN,
          'kategorien': models.ZUTATENKATEGORIEN,
        })
        if len(param)>0 and self.isauthorized():
            zutat = db.get(db.Key(param[0]))
            template_values['zutat'] = zutat
            template_values['rezepte'] = [r for r in zutat.verwendung]
            htmlfile = 'zutat-bearbeiten.html'
        else:
            htmlfile = 'zutaten.html'
        zutaten = db.GqlQuery("SELECT * FROM Zutat ORDER BY kategorie, name")
        template_values['zutaten'] = zutaten

        self.write_out_template(htmlfile, template_values)

class ZutatLoeschen(AuthorizedRequestHandler):
    def get(self, zutatkey):
        if self.authorize():
            zutat = db.get(db.Key(zutatkey))
            if zutat:
                zutat.delete()
            self.redirect('/zutaten')

class RezeptEingabe(AuthorizedRequestHandler, TemplateWriter):
    def get(self):
        if self.authorize():
            zutaten = models.Zutat.all().order("name").fetch(1000)
            zutaten = dict([(k or u'keine Kategorie',
                             [z for z in zutaten if z.kategorie == k])
                            for k in set([z.kategorie for z in zutaten])])
            template_values = standard_template_values()
            template_values.update({
              'zutaten': zutaten,
              'gaenge': GAENGE,
              'kategorien': REZEPTKATEGORIEN,
            })
            self.write_out_template('rezept-eingeben.html', template_values)

    def post(self):
        rezept = models.makeRezeptFromRequest(self.request)
        rezept.put()

        zutaten = self.request.get('zutatensammlung')
        if len(zutaten)>1:
            #logging.debug('zutaten = ' + zutaten)
            zutaten = zutaten[:-1].split(u'|')
            #logging.debug('zutaten[0] = ' + zutaten[0])
            nr = 1
            for z in zutaten:
                #logging.debug('z = %s, nr = %d' % (z, nr))
                z = z.split(u'§')
                name = z[0]
                key = z[1]
                menge = z[2]
                menge_qual = z[3]
                zutat = db.Key(key)
                if menge_qual:
                    menge = None
                else:
                    menge = float(menge)
                    menge_qual = None
                rz = models.RezeptZutat()
                rz.init(rezept.key(), zutat, menge, menge_qual, nr)
                rz.put()
                nr += 1
        self.redirect('/rezepte/%s' % rezept.id)

class RezepteAnzeigen(webapp.RequestHandler, TemplateWriter):
    def get(self, mitPreis = False):
        class Kategorie():
            pass
        kategorien = {}
        namen = list(REZEPTKATEGORIEN) + [
                u'keine Kategorie', u'Vorspeise', u'Nachtisch']
        for kategorie in namen:
            k = Kategorie()
            k.kategorie = kategorie
            k.rezepte = []
            kategorien[kategorie] = k
        rezepte = models.Rezept.all().order('titel')
        rezepte = rezepte.fetch(1000)
        for r in rezepte:
            if not r.typ or u'Hauptgang' in r.typ:
                kategorien[r.kategorie or u'keine Kategorie'].rezepte.append(r)
            for g in (u'Vorspeise', u'Nachtisch'):
                if g in r.typ:
                    kategorien[g].rezepte.append(r)
        for k in kategorien.values():
            k.anzahl = len(k.rezepte)
        hauptspeisen = [kategorien[n] for n in namen[:-2] if kategorien[n].anzahl]
        vornachspeisen = [kategorien[n] for n in namen[-2:] if kategorien[n].anzahl]
        template_values = standard_template_values()
        template_values.update({
          'hauptspeisen': hauptspeisen,
          'vornachspeisen': vornachspeisen,
          'allerezepte': rezepte,
        })
        if mitPreis:
            self.write_out_template('rezepte-anzeigen-mit-preis.html', template_values)
        else:
            self.write_out_template('rezepte-anzeigen.html', template_values)

class RezepteAnzeigenMitPreis(RezepteAnzeigen):
    def get(self):
        super(RezepteAnzeigenMitPreis, self).get(mitPreis = True)

class RezeptAnzeigen(webapp.RequestHandler, TemplateWriter):
    def get(self, *param):
        try:
            rezept, anzahlversionen = getRezept(*param)
        except NotFoundError, e:
            self.response.out.write(e.msg)
            self.response.set_status(404)
            return
        template_values = standard_template_values()
        template_values.update({
          'rezept': rezept,
          'kinder': rezept.personen[0],
          'erwachsene': rezept.personen[1],
          'zutaten': [(zutat.toStr(), zutat.preisToStr()) \
                      for zutat in rezept.zutaten],
          'preis': rezept.preis(),
          'gang': ', '.join(rezept.typ),
          'anzahlversionen': anzahlversionen,
        })
        self.write_out_template('rezept-anzeigen.html', template_values)

class RezeptBearbeiten(AuthorizedRequestHandler, TemplateWriter):
    def get(self, *param):
        if self.authorize():
            try:
                rezept, anzahlversionen = getRezept(*param)
            except NotFoundError, e:
                self.response.out.write(e.msg)
                self.response.set_status(404)
                return
            zutaten = db.GqlQuery("SELECT * FROM Zutat ORDER BY kategorie, name")
            zutatennachkategorien = dict([(k or u'keine Kategorie',
                [z for z in zutaten if z.kategorie == k])
                for k in set([z.kategorie for z in zutaten])])
            template_values = standard_template_values()
            template_values.update({
                'rezept': rezept,
                'kinder': rezept.personen[0],
                'erwachsene': rezept.personen[1],
                'zutaten': zutatennachkategorien,
                'zutatkategorien': models.ZUTATENKATEGORIEN,
                'preis': rezept.preis(),
                'gaenge': GAENGE,
                'kategorien': REZEPTKATEGORIEN,
                'anzahlversionen': anzahlversionen,
            })
            self.write_out_template('rezept-bearbeiten.html', template_values)

    def post(self, *param):
        #id = param[0]
        rezept = db.get(db.Key(self.request.get('rezeptkey')))
        rezept.titel = self.request.get('titel')
        rezept.calculateId(rezept.titel)
        rezept.kommentar = self.request.get('kommentar')
        rezept.personen = [long(self.request.get('kinder')),
                           long(self.request.get('erwachsene'))]
        rezept.zubereitung = self.request.get('zubereitung')
        rezept.anmerkungen = self.request.get('anmerkungen')
        rezept.typ = self.request.get_all('gang')
        rezept.kategorie = self.request.get('kategorie')
        rezept.put()
        self.redirect('/rezepte/%s/%s' % (param[0],
                                          len(param)>1 and param[1] or '1'))

class RezeptLoeschen(AuthorizedRequestHandler):
    def get(self, key):
        if self.authorize():
            rezept = db.get(db.Key(key))
            zutaten = rezept.zutaten.fetch(100)
            db.delete(zutaten)
            rezept.delete()
            self.redirect('/rezepte')

class RezeptBuch(AuthorizedRequestHandler, TemplateWriter):
    def get(self):
        if self.authorize():
            rezepte = models.Rezept.all().order("kategorie"
                                        ).order("titel"
                                        ).fetch(1000)
            rezepte_d = dict([(r.key(), r) for r in rezepte])
            for r in rezepte:
                r.zutatenliste = []
            for z in models.RezeptZutat.all().run(batch_size=1000):
                rezepte_d[models.RezeptZutat.rezept.get_value_for_datastore(z)
                          ].zutatenliste.append(z.toStr())
            rez = [{"gang": g,
                    "rezepte": [r for r in rezepte if g in r.typ]}
                   for g in GAENGE]
            self.write_out_template('rezeptbuch.html', {'rezepte': rez})


class Monatsplan(webapp.RequestHandler, TemplateWriter):
    def get(self, jahr=None, monat=None):
        # jetziger Monat als default
        try:
            monat, jahr = int(monat), int(jahr)
            if jahr<2000:
                jahr += 2000
        except (TypeError, ValueError):
            today = date.today()
            monat, jahr = today.month, today.year
        erster = date(jahr, monat, 1)
        naechstererster = (monat<12) and date(jahr, monat+1, 1) or date(jahr+1, 1, 1)
        vorigererster = (monat>1) and date(jahr, monat-1, 1) or date(jahr-1, 12, 1)
        anzahltage = (naechstererster - erster).days
        class Tag():
            def __init__(self, jahr, monat, tag):
                self.tag = date(jahr, monat, tag)
                self.feiertag = self.tag.weekday() > 4 # Sa + So
                self.klasse = 'Feiertag' if self.feiertag else 'Menue'
        tage = [Tag(jahr, monat, tag) for tag in range(1, anzahltage+1)]
        qtage = models.Tagesplan.all().filter('datum >=', erster
                                     ).filter('datum <', naechstererster
                                     ).order('datum')
        for plan in qtage:
            # Verweise auf gelöschte Rezepte entfernen
            for gang in ('vorspeise', 'hauptgang', 'nachtisch'):
                try:
                    getattr(plan, gang)
                except:
                    setattr(plan, gang, None)
                    plan.put()
        for plan in qtage:
            tag = tage[(plan.datum - erster).days]
            tag.klasse = plan.class_name()
            tag.menue = plan

        # Rezepte zur Auswahl
        hauptgangrezepte = models.Rezept.all().filter('typ =', 'Hauptgang')
        hauptgangrezepte.order('titel')
        template_values = standard_template_values()
        template_values.update({
            'monat': monat,  # int
            'jahr': jahr,    # int
            'tage': tage,    # array mit tag (date), feiertag (bool)
                             # klasse ("Feiertag", "Menue")
                             # menue (Feiertag, Menue)
            'gaenge': [
                (u'vorspeise', models.Rezept.all().filter('typ =', 'Vorspeise').order('titel')),
                (u'hauptgang', hauptgangrezepte),
                (u'nachtisch', models.Rezept.all().filter('typ =', 'Nachtisch').order('titel')),
            ],
        })
        # Links zum nächsten und vorigen Monat
        # in späteren Djangoversionen übernimmt das die Templatesprache
        MONATE = (u"Januar", u"Februar", u"März", u"April", u"Mai", u"Juni",
                  u"Juli", u"August", u"September", u"Oktober", u"November",
                  u"Dezember")
        for mname, m in (('vormonat', vorigererster),
                         ('naechstermonat', naechstererster)):
            logging.error('mname: ' + mname)
            logging.error('m: ' + str(m))
            template_values[mname] = {'name': ('%s %d' % (MONATE[m.month-1],
                                                          m.year)),
                'link': '/monatsplan/%d/%d' % (m.year, m.month)}
            logging.error(repr(template_values[mname]))
        self.write_out_template('monatsplan.html', template_values)

class Menueplan(webapp.RequestHandler, TemplateWriter):
    def get(self, jahr, monat, tag):
        datum = date(int(jahr), int(monat), int(tag))
        menue = models.Menue.all().filter('datum =', datum).get()
        template_values = standard_template_values()
        template_values['datum'] = datum
        if not menue:
            template_values['fehlermeldung'] = u'Menü nicht gefunden'
        else:
            template_values['koch'] = menue.koch
            rezepte = []
            for gang in (u'vorspeise', u'hauptgang', u'nachtisch'):
                rezept = getattr(menue, gang, None)
                if rezept:
                    rezepte.append({
                        'gang': gang.capitalize(),
                        'rezept': rezept,
                        'kinder': rezept.personen[0],
                        'erwachsene': rezept.personen[1],
                    })
            template_values['rezepte'] = rezepte
        self.write_out_template('menueplan.html', template_values)

def rezeptliste(beginn, dauer):
    tage = models.Menue.all()
    tage.filter('datum >=', beginn).filter('datum <', beginn + timedelta(dauer))
    rezepte = [] # Für "Folgende Rezepte wurden geplant"
    messbar = {} # Die Zutaten mit quantitativer Mengenangabe
    einheiten = {}
    qualitativ = {} # Die Zutaten mit qualitativer Mengenangabe
    rezeptzutaten = {}
    for t in tage:
        for r in (t.vorspeise, t.hauptgang, t.nachtisch):
            if r:
                rezepte.append(r)
                for rz in r.zutaten:
                    rzzutat = rz.zutat
                    zutatkey = str(rzzutat.key())
                    rezeptzutaten[zutatkey] = rzzutat
                    zt = rzzutat.name
                    if rz.menge:
                        if zutatkey in messbar.keys():
                            messbar[zutatkey] += rz.menge
                        else:
                            messbar[zutatkey] = rz.menge
                    elif rz.menge_qualitativ:
                        if not zutatkey in qualitativ.keys():
                            qualitativ[zutatkey] = []
                        qualitativ[zutatkey].append(rz.menge_qualitativ)
    messbarkat = dict([(kat, []) for kat in models.ZUTATENKATEGORIEN])
    for zk, menge in messbar.items():
        zutat = rezeptzutaten[zk]
        messbarkat[zutat.kategorie].append({'name': zutat.name,
                     'menge': tools.prettyFloat(menge),
                     'einheit': zutat.masseinheit,
                     'key': str(zk)})
    for z in messbarkat.values():
        z.sort(lambda x,y: cmp(x["name"].lower(), y["name"].lower()))
    qualitativkat = dict([(kat, []) for kat in models.ZUTATENKATEGORIEN])
    for zk, menge in qualitativ.items():
        zutat = rezeptzutaten[zk]
        qualitativkat[zutat.kategorie].append({'name': zutat.name,
                     'menge': ', '.join(menge),
                     'key': str(zk)})
    for z in qualitativkat.values():
        z.sort(lambda x,y: cmp(x["name"].lower(), y["name"].lower()))
    rezepte.sort(lambda x,y: cmp(x.titel.lower(), y.titel.lower()))

    res = standard_template_values()
    res.update({'dauer': dauer,
        'beginn': beginn,
        'rezepte': rezepte,
        'messbar': messbarkat,
        'qualitativ': qualitativkat,
    })
    return res

class Einkaufsliste(webapp.RequestHandler, TemplateWriter):
    def get(self, *param):
        bisdienstag = 8 - date.today().weekday()
        if bisdienstag >6:
            bisdienstag -= 7
        beginn = date.today() + timedelta(bisdienstag)
        dauer = 7
        try:
            b, d = "", 0
            # Aufruf mit '/einkaufsliste/20.09.2009/7'?
            if len(param)>1:
                b = param[0]
                d = int(param[1])
            # Aufruf aus Formdaten?
            temp = self.request.get('beginn')
            if temp:
                b = temp
            temp = self.request.get('dauer')
            if temp:
                d = int(temp)
            beginn = tools.str2date(b)
            dauer = d
        except (IndexError, ValueError):
            pass
        self.write_out_template('einkaufsliste.html', rezeptliste(beginn, dauer))

class DatenAusgabe(webapp.RequestHandler):
    def get(self):
        write = self.response.out.write
        write(["""#coding: utf-8
from google.appengine.dist import use_library
use_library("django", "1.0")
import os
from google.appengine.ext import db
import datetime
import models
def apply_fixture():
    if not os.environ['SERVER_SOFTWARE'].startswith('Development'):
        return
    rezepte = models.Rezept.all().fetch(200)
    zutaten = models.Zutat.all().fetch(200)
    rz = models.RezeptZutat.all().fetch(200)
    menues = models.Menue.all().fetch(200)
    db.delete(rezepte + zutaten + rz + menues)
"""])
        for entitaet in (models.Zutat, models.Rezept, models.RezeptZutat, models.Menue):
            for e in entitaet.all():
                write(e.initString())
                write('\n')

class Impressum(webapp.RequestHandler, TemplateWriter):
    def get(self):
        self.write_out_template('impressum.html', None)

class Fixture(AuthorizedRequestHandler):
    def get(self):
        if not os.environ['SERVER_SOFTWARE'].startswith('Development'):
            logging.error('Fixture darf nur auf dem Developmentserver aufgerufen werden.')
        elif not self.authorize():
            logging.error('Fixture: Der Benutzer ist nicht angemeldet.')
        else:
            import fixture
            fixture.apply_fixture()
        self.redirect('/monatsplan')

class SiteVerification(webapp.RequestHandler):
    def get(self):
        self.response.out.write('google-site-verification: googleea70c6ff94a550df.html')

urls = [
        ('/', MainPage),
        ('/index.html', MainPage),
        ('/googleea70c6ff94a550df.html', SiteVerification),
        (r'/zutaten/(.+)', ZutatenEingabe),
        (r'/zutaten', ZutatenEingabe),
        (r'/zutatloeschen/(.+)', ZutatLoeschen),
        (r'/rezepteingabe/?', RezeptEingabe),
        (r'/rezepteingabe/(.+)/(.+)/?', RezeptBearbeiten),
        (r'/rezepteingabe/(.+)/?', RezeptBearbeiten),
        (r'/rezeptloeschen/(.+)/?', RezeptLoeschen),
        (r'/rezepte/?', RezepteAnzeigen),
        (r'/rezepte-mit-preis/?', RezepteAnzeigenMitPreis),
        (r'/rezepte/(.+)/(.+)/?', RezeptAnzeigen),
        (r'/rezepte/(.+)/?', RezeptAnzeigen),
        (r'/rezeptbuch/?', RezeptBuch),
        (r'/monatsplan/?', Monatsplan),
        (r'/monatsplan/(.+)/(.+)/?', Monatsplan),
        (r'/menueplan/(.+)/(.+)/(.+)/?', Menueplan),
        (r'/einkaufsliste/(.+)/(.+)/?', Einkaufsliste),
        (r'/einkaufsliste/(.+)/?', Einkaufsliste),
        (r'/einkaufsliste/?', Einkaufsliste),
        (r'/daten/?', DatenAusgabe),
        (r'/impressum/?', Impressum),
        (r'/fixture/?', Fixture),
        ]

import ajax
application = webapp.WSGIApplication(urls + ajax.urls,
                                     debug=True)

def main():
    logging.getLogger().setLevel(logging.DEBUG)
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
