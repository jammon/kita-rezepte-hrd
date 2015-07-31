# coding: utf-8
import logging
import datetime
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext.db import polymodel
import tools

MASSEINHEITEN = [u"g", u"ml", u"St.", u"Pckg."]
ZUTATENKATEGORIEN = [u"Milchprodukt", u"Gemüse", u"Obst", u"Getreide",
                     u"Grundnahrungsmittel", u"Fisch", u"Gewürz", u"Sonstiges"]


class Zutat(db.Model):
    """ Eine Zutat, die in den Rezepten verwandt werden kann

    name: Name (naja)
    einheit: Packungseinheit für den Einkauf meist 1 kg, 1 l, aber auch
             2,5 kg-Sack.
             Fällt weg bei Dingen wie Eiern, die eine natürliche Einheit
             haben; dann "Stück"
    preis_pro_einheit: der Preis einer Packungseinheit; in Cent
    menge_pro_einheit: Anzahl der "masseinheit"en (s.u.) pro Packungseinheit
    masseinheit: (s.o.)
    kategorie: Grundnahrungsmittel, Obst, usw.
    """
    name = db.StringProperty()
    einheit = db.StringProperty()
    preis_pro_einheit = db.IntegerProperty()  # Angabe in Cent
    menge_pro_einheit = db.IntegerProperty()  # bei 1 kg: 1000
    masseinheit = db.StringProperty(choices=MASSEINHEITEN)  # bei 1 kg: g
    kategorie = db.StringProperty(choices=ZUTATENKATEGORIEN)

    def preisInEuro(self):
        """ Preis einer Packungseinheit in Euro als String

        z.B. "3,59"
        """
        res = u"%.2f" % (self.preis_pro_einheit/100.0, )
        return res.replace('.', ',')

    def einHeit(self):
        if self.menge_pro_einheit:
            return self.masseinheit
        else:
            return self.einheit

    def initString(self):
        """Gib einen Python-Befehl zurück, mit dem das Objekt in einer Fixture
        wieder gebaut werden kann
        """
        res = u'    models.Zutat(key_name=u"%s", name=u"%s", einheit=u"%s", ' + \
              u'preis_pro_einheit=%d, menge_pro_einheit=%d, ' + \
              u'masseinheit=u"%s", kategorie=u"%s").put()'
        return res % (unicode(self.key()), self.name, self.einheit,
                      self.preis_pro_einheit or 0, self.menge_pro_einheit or 0,
                      self.masseinheit or '', self.kategorie or '',)

    def updateRezeptpreise(self):
        """ Wenn der Preis einer Zutat geändert wurde, müssen die Rezeptpreise entsprechend
        angepasst werden.
        """
        for rz in self.verwendung:
            rz.rezept.preis(update=True)


class Rezept(db.Model):
    '''Enthält ein Rezept mit Titel, Kochanweisung usw.
       Die Zutaten werden getrennt davon mit dem Key des Rezepts gespeichert
       (Model RezeptZutat).
    '''
    titel = db.StringProperty()
    id = db.StringProperty()  # wird i.d.R. aus titel berechnet
    kommentar = db.TextProperty()
    personen = db.ListProperty(long)  # Anzahl der [Kinder, Erwachsenen]
    zubereitung = db.TextProperty()
    anmerkungen = db.TextProperty()
    eingegeben_von = db.UserProperty()
    typ = db.StringListProperty()    # Vorspeise, Hauptgang, Nachtisch
                                     # kann mehrere Werte enthalten
    kategorie = db.StringProperty()  # Art des Essens
    # z.B. Gemüse, Teigwaren, Suppe, Getreide, Reis usw.
    version = db.IntegerProperty()  # Es kann mehrere Versionen dieses Rezepts geben
    preis_ = db.FloatProperty()  # kann leer sein, dann wird er neu berechnet

    def init(self, titel=None, kommentar=None, personen=None,
             zubereitung=None, anmerkungen=None,
             typ=None, kategorie=None, id=None, version=1):
        #db.Model.__init__(self)
        self.titel = titel
        self.calculateId(titel)
        self.kommentar = kommentar
        self.personen = personen
        self.zubereitung = zubereitung
        self.anmerkungen = anmerkungen
        self.eingegeben_von = users.get_current_user()
        self.typ = typ
        self.kategorie = kategorie
        self.version = version

    def calculateId(self, titel):
        """Sucht eine ID, die aus dem Titel erstellt wird und noch nicht
        vergeben ist.
        """
        grund_id = id = tools.str2id(titel)
        vorhandeneIds = []
        # Alle IDs raussuchen, die mit grund_id anfangen
        query = Rezept.all().filter('id >= ', id).order('id')
        for r in query:
            if self.is_saved() and (r.key() == self.key()):
                continue
            if r.id.startswith(grund_id):
                vorhandeneIds.append(r.id)
            else:
                break
        i = 0
        while id in vorhandeneIds:
            i += 1
            id = grund_id + str(i)
        self.id = id

    def preis(self, update=False):
        """ Gibt den vorberechneten Preis oder rechnet ihn neu
        """
        if self.preis_ is None or update:
            self.preis_ = sum([zutat.preis() for zutat in self.zutaten])/100.0
            if self.is_saved():
                self.put()
        return self.preis_

    def preisToStr(self):
        """ Gibt den Preis als String (z.B. '13,48 €')
        """
        return u"%.2f&nbsp;&euro;" % (self.preis(),)

    def initString(self):
        """Gib einen Python-Befehl zurück, mit dem das Objekt in einer Fixture
        wieder gebaut werden kann
        """
        res = u'    models.Rezept(key_name=u"%s", titel=u"%s", id=u"%s", ' + \
              u'kommentar="""%s""", personen=%s, zubereitung=u"""%s""", ' + \
              u'anmerkungen=u"""%s""", typ=[u"%s"], ' + \
              u'kategorie=u"%s", version=%d).put()'
        return res % (unicode(self.key()), self.titel, self.id, self.kommentar,
                      unicode(self.personen), self.zubereitung, self.anmerkungen,
                      '", u"'.join(self.typ), self.kategorie, self.version or 1,)


def makeRezeptFromRequest(request):
    r = Rezept()
    r.titel = request.get('titel')
    r.kommentar = request.get('kommentar')
    r.personen = [long(request.get('kinder')), long(request.get('erwachsene'))]
    r.zubereitung = request.get('zubereitung')
    r.anmerkungen = request.get('anmerkungen')
    r.typ = request.get_all('gang')
    r.kategorie = request.get('kategorie')
    r.version = 1
    r.calculateId(r.titel)
    return r


class RezeptZutat(db.Model):
    """Eine Zutat, die in einem Rezept verwendet wird.

    Enthält
    - rezept, zutat: einen Verweis auf das Rezept und die Zutat
    - menge, menge_qualitativ: die gewünschte Menge als Float oder qualitativ als String
    - name, einheit: Name und Einheit der Zutat, um DB-Zugriffe zu sparen
    - nummer: eine Nummer, um die Zutaten sortieren zu können
    """
    rezept = db.ReferenceProperty(Rezept, collection_name='zutaten')
    zutat = db.ReferenceProperty(Zutat, collection_name='verwendung')
    menge = db.FloatProperty()
    menge_qualitativ = db.StringProperty()
    name = db.StringProperty()
    einheit = db.StringProperty()
    nummer = db.IntegerProperty()

    def init(self, rezept, zutat, menge, menge_qualitativ, nummer):
        db.Model.__init__(self)
        if type(rezept) in (db.Key, Rezept):
            self.rezept = rezept
        else:
            self.rezept = Rezept.all().filter('id = ', rezept).get()
        if type(zutat) not in (db.Key, Zutat):
            zutat = Zutat.all().filter('name = ', zutat).get()
        self.zutat = zutat
        self.name = self.zutat.name
        self.menge = menge
        self.einheit = self.zutat.einHeit()
        self.menge_qualitativ = menge_qualitativ
        self.nummer = nummer

    def initString(self):
        """Gib einen Python-Befehl zurück, mit dem das Objekt in einer Fixture
        wieder gebaut werden kann
        """
        res = u'    models.RezeptZutat(rezept=models.Rezept.get_by_key_name(u"%s"), ' + \
              u'zutat=models.Zutat.get_by_key_name(u"%s"), name=u"%s", menge=%s, ' + \
              u'einheit=u"%s", menge_qualitativ=u"%s", nummer=%d).put()'
        return res % (unicode(self.rezept.key()), unicode(self.zutat.key()), self.name,
                      unicode(self.menge or None), self.einheit or u'',
                      self.menge_qualitativ or '', self.nummer or 1)

    def toStr(self):
        liste = (self.menge_qualitativ and [self.menge_qualitativ] or
                 [tools.prettyFloat(self.menge), self.einheit or ''])
        liste.append(self.name)
        return ' '.join(liste)

    def __str__(self):
        return self.toStr()

    def preis(self):
        '''Gibt den Preis der Zutat in Cent'''
        if self.menge_qualitativ:
            return 0
        z = self.zutat
        if not z.preis_pro_einheit:
            return 0
        if z.menge_pro_einheit:
            return long(self.menge * z.preis_pro_einheit / z.menge_pro_einheit)
        else:
            return long(self.menge * z.preis_pro_einheit)

    def preisToStr(self):
        return u'%.2f €' % (self.preis()/100.0,)


class MenueBewertung(db.Model):
    datum = db.DateProperty()
    eingegeben_von = db.UserProperty()
    hat_geschmeckt = db.RatingProperty()
    menge_ok = db.RatingProperty()
    kommentar = db.TextProperty()


# abstrakte Grundklasse
class Tagesplan(polymodel.PolyModel):
    datum = db.DateProperty()


class Feiertag(Tagesplan):
    kommentar = db.StringProperty()


class Menue(Tagesplan):
    """ Speichert drei Rezepte (Vorspeise, Hauptgang und Nachtisch),
    einen Koch und eine Bewertung

    Zusätzlich werden Listen der Gänge, Titel der Gänge und Preise der Gänge gespeichert.
    Die Änderungsoperationen sollen immer auf den einzelnen Rezept-Properties erfolgen.
    """
    koch = db.StringProperty()
    vorspeise = db.ReferenceProperty(Rezept, collection_name="vorspeise")
    hauptgang = db.ReferenceProperty(Rezept, collection_name="hauptgang")
    nachtisch = db.ReferenceProperty(Rezept, collection_name="nachtisch")
    bewertung = db.ReferenceProperty(MenueBewertung)
    titel = db.StringListProperty(default=['', '', ''])
    preise = db.ListProperty(float, default=[0.0, 0.0, 0.0])
    has_lists = db.BooleanProperty(default=False)

    def put(self, *args, **kwargs):
        gaenge = [self.vorspeise, self.hauptgang, self.nachtisch]
        self.titel = [(gang is not None and gang.titel or '') for gang in gaenge]
        self.preise = [(gang is not None and gang.preis() or 0.0) for gang in gaenge]
        self.has_lists = True
        return super(Menue, self).put(*args, **kwargs)

    def initString(self):
        """Gib einen Python-Befehl zurück, mit dem das Objekt in einer Fixture
        wieder gebaut werden kann
        """
        res = u'    models.Menue(datum= datetime.date.fromordinal(%d), ' + \
              u'koch = %s, vorspeise=%s, hauptgang=%s, nachtisch=%s, ' + \
              u'bewertung=None).put()'
        return res % (self.datum.toordinal(),
            self.koch and ('"'+self.koch+'"') or 'None',
            self.vorspeise and ('models.Rezept.get_by_key_name(u"%s")' %
                                (str(self.vorspeise.key()),)) or 'None',
            self.hauptgang and ('models.Rezept.get_by_key_name(u"%s")' %
                                (str(self.hauptgang.key()),)) or 'None',
            self.nachtisch and ('models.Rezept.get_by_key_name(u"%s")' %
                                (str(self.nachtisch.key()),)) or 'None', )

    def get_gang(self, nr):
        return getattr(self, ('vorspeise', 'hauptgang', 'nachtisch')[nr])
    def get_gang_titel(self, nr):
        if self.has_lists:
            return self.titel[nr]
        gang = self.get_gang(nr)
        logging.debug('get_gang_titel gang: %s'%repr(gang))
        return gang and gang.titel or ''
    def get_gang_titel_mit_preis(self, nr):
        if self.has_lists:
            titel, preis = self.titel[nr], self.preise[nr]
        else:
            gang = self.get_gang(nr)
            if gang is not None:
                titel, preis = gang.titel, gang.preis()
            else:
                titel, preis = '', 0.0
        return titel and (u"%s %.2f €" % (titel, preis)) or ''
    def get_vorspeise(self):
        titel = self.get_gang_titel(0)
        return titel
    def get_vorspeise_mit_preis(self):
        res = self.get_gang_titel_mit_preis(0)
        return res
    def get_hauptgang(self):
        return self.get_gang_titel(1)
    def get_hauptgang_mit_preis(self):
        return self.get_gang_titel_mit_preis(1)
    def get_nachtisch(self):
        return self.get_gang_titel(2)
    def get_nachtisch_mit_preis(self):
        return self.get_gang_titel_mit_preis(2)


class MonatsPlan(db.Model):
    """Speicher fuer einen MonatsPlan, um DB-Zugriffe zu reduzieren"""
    monat = db.IntegerProperty()
    jahr = db.IntegerProperty()
    tage = db.StringListProperty()
    tage_auth = db.StringListProperty()


def getMonatsPlan(monat, jahr):
    monatsplan = MonatsPlan.all().filter("monat =", monat
                                ).filter("jahr =", jahr
                                ).get()
    if monatsplan:
        return monatsplan
    erster = datetime.date(jahr, monat, 1)
    naechstererster = ((monat<12) and datetime.date(jahr, monat+1, 1)
                       or datetime.date(jahr+1, 1, 1))
    FEIERTAG = "<td>%(tag)d.</td><td colspan='4'></td>"
    WTAG = ("<td><a href='/menueplan/%(jahr)d/%(monat)d/%(tag)d'>%(tag)d.</a></td>"
            "<td class='koch'><span id='koch_%(tag)d'>%(koch)s</span></td>"
            "<td class='vorspeise'><span id='vorspeise_%(tag)d'>%(vorspeise)s</span></td>"
            "<td class='hauptgang'><span id='hauptgang_%(tag)d'>%(hauptgang)s</span></td>"
            "<td class='nachtisch'><span id='nachtisch_%(tag)d'>%(nachtisch)s</span></td>")
    params = {'jahr': jahr,
        'monat': monat,
        'koch': '',
        'vorspeise': '',
        'hauptgang': '',
        'nachtisch': '',
        }
    # to be cont'd
