# coding: utf-8
from google.appengine.dist import use_library
use_library('django', '1.0')
import os
from datetime import date
from exceptions import ValueError

from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

import logging
import models

class EditMenue(webapp.RequestHandler):
    def post(self, spalte, jahr, monat):
        id = self.request.get('id')
        value = self.request.get('value')
        tag = int(id[id.index(u'_')+1:])
        jahr, monat = int(jahr), int(monat)
        if jahr<2000:
            jahr += 2000
        datum = date(jahr, monat, tag)
        menue = models.Menue.all().filter('datum =', datum).get()
        if not menue:
            menue = models.Menue()
            menue.datum = datum
        if spalte == 'koch':
            menue.koch = value
        else:
            rezept = models.Rezept.all().filter('id =', value).get()
            if spalte == 'vorspeise':
                menue.vorspeise = rezept
            elif spalte == 'hauptgang':
                menue.hauptgang = rezept
            elif spalte == 'nachtisch':
                menue.nachtisch = rezept
            value = u"%s %s" % (rezept.titel, rezept.preisToStr())
        menue.put()
        self.response.out.write(value)

class EditRezept(webapp.RequestHandler):
    def post(self, rezeptid):
        id = self.request.get('id')
        value = self.request.get('value')
        rezept = models.Rezept.all().filter('id =', rezeptid).get()
        if id == 'titel':
            rezept.titel = value
        elif id == 'untertitel':
            rezept.kommentar = value
        elif id == 'zubereitung':
            rezept.zubereitung = value
        elif id == 'anmerkungen':
            rezept.anmerkungen = value
        elif id == 'rezept_gang':
            rezept.typ = value
        elif id == 'kategorie':
            rezept.kategorie = value
        elif id == 'kinder':
            rezept.personen[0] = int(value)
        elif id == 'erwachsene':
            rezept.personen[1] = int(value)
        else:
            raise ValueError('EditRezept wurde mit falscher id aufgerufen: %s' % (id,))
        rezept.put()
        self.response.out.write(value)

class DeleteRezept(webapp.RequestHandler):
    def post(self, rezeptid):
        rezept = models.Rezept.all().filter('id =', rezeptid).get()
        for zutat in rezept.zutaten():
            zutat.delete()
        rezept.delete()

class EditZutatPreis(webapp.RequestHandler):
    def post(self):
        id = self.request.get('id')
        value = self.request.get('value')
        zutat = models.Zutat.all().filter('__key__ =', db.Key(id)).get()
        preis = value.replace(',', '.')
        zutat.preis_pro_einheit = int(round(100*float(preis)))
        zutat.put()
        zutat.updateRezeptpreise()
        self.response.out.write(value)
        

class EditZutatKategorie(webapp.RequestHandler):
    def post(self):
        pass
#        id = self.request.get('id')
#        value = self.request.get('value')
#        zutat = models.Zutat.all().filter('__key__ =', db.Key(id)).get()
#        preis = value.replace(',', '.')
#        zutat.preis_pro_einheit = int(round(100*float(preis)))
#        zutat.put()
#        self.response.out.write(value)

class ZutatHinzufuegen(webapp.RequestHandler):
    def post(self):
        rezept = db.get(db.Key(self.request.get('rezept')))
        zutat = db.get(db.Key(self.request.get('zutat')))
        if not rezept:
            logging.error('ZutatHinzufuegen hat Rezept %s nicht gefunden.' % self.request.get('rezept'))
        if not zutat:
            logging.error('ZutatHinzufuegen hat Zutat %s nicht gefunden.' % self.request.get('zutat'))
        menge = self.request.get('menge')
        rz = models.RezeptZutat()
        try:
            menge = float(menge)
            rz.init(rezept, zutat, menge, '', 0)
        except ValueError:
            rz.init(rezept, zutat, 0.0, menge, 0)
        rz.put()
        rezept.preis(update = True)
        self.response.out.write('<tr><td>%s</td><td>%s</td><td></td></tr>' % (rz.toStr(), rz.preisToStr()))


class ZutatLoeschen(webapp.RequestHandler):
    def post(self):
        zutat = db.get(db.Key(self.request.get('zutat')))
        zutat.delete()
        zutat.rezept.preis(update = True)
        self.response.out.write('ok')

urls = [(r'/ajax/menue/(.+)/(.+)/(.+)', EditMenue),
        (r'/ajax/deleterezept/(.+)', EditRezept),# XXX: muss wohl DeleteRezepte heißen
        (r'/ajax/rezept/(.+)', EditRezept),
        (r'/ajax/zutat/preis', EditZutatPreis),
        (r'/ajax/zutat/kategorie', EditZutatKategorie),
        (r'/ajax/zutat/hinzufuegen', ZutatHinzufuegen),
        (r'/ajax/zutat/loeschen', ZutatLoeschen),]

#application = webapp.WSGIApplication(urls,
#                                     debug=True)
#
#def main():
#    run_wsgi_app(application)
#
#if __name__ == "__main__":
#    main()