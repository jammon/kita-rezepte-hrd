# coding: utf-8
from google.appengine.dist import use_library
use_library('django', '1.0')
import os

from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

class AuthorizedUser(db.Model):
    """Represents authorized users in the datastore."""
    user = db.UserProperty()


class AuthorizedRequestHandler(webapp.RequestHandler):
    """Authenticate users against a stored list of authorized users.

    Base your request handler on this class and check the authorize() method
    for a True response before processing in get(), post(), etc. methods.

    For example:

    class Test(AuthorizedRequestHandler):
        def get(self):
            if self.authorize():
                self.response.out.write('You are an authenticated user.')
    """
    
    def authorization_status(self):
        """Return one of 'NOT_LOGGED_IN', 'NOT_AUTHORIZED' and 'AUTHORIZED'
        
        Hits the database for every call. 
        TODO: Cache the AuthorizedUsers with Memcache
        """ 
        user = users.get_current_user()
        if not user:
            return 'NOT_LOGGED_IN'
        else:
            auth_user = AuthorizedUser.gql("where user = :1", user).get()
            if not auth_user:
                return 'NOT_AUTHORIZED'
            else:
                return 'AUTHORIZED'

    def authorize(self):
        """Return True if user is authenticated.
        """
        status = self.authorization_status()
        if status == 'NOT_LOGGED_IN':
            self.not_logged_in()
        elif status == 'NOT_AUTHORIZED':
            self.unauthorized_user()
        elif status == 'AUTHORIZED':
            return True

    def isauthorized(self):
        """ Returns True if the current user is authorized
        """
        return self.authorization_status() == 'AUTHORIZED'

    def not_logged_in(self):
        """Action taken when user is not logged in (default: go to login screen)."""
        self.redirect(users.create_login_url(self.request.uri))

    def unauthorized_user(self):
        """Action taken for unauthenticated  user (default: go to error page)."""
        self.response.out.write("""
            <html>
              <body>
                <div>Unauthorized User</div>
                <div><a href="%s">Logout</a>
              </body>
            </html>""" % users.create_logout_url(self.request.uri))

class ManageAuthorizedUsers(webapp.RequestHandler):
    """Manage list of authorized users through web page.

    The GET method shows page with current list of users and allows
    deleting user or adding a new user by email address.

    The POST method handles adding a new user.
    """

    template_file = 'html/auth.html'
    
    def get(self):
        template_values = {
            'authorized_users': AuthorizedUser.all()
            }
        path = os.path.join(os.path.dirname(__file__), self.template_file)
        self.response.out.write(template.render(path, template_values))

    def post(self):
        email = self.request.get('email').strip()
        user = users.User(email)
        auth_user = AuthorizedUser()
        auth_user.user = user
        auth_user.put()
        self.redirect('/auth/users')


class DeleteAuthorizedUser(webapp.RequestHandler):
    """Delete an authorized user from the datastore."""
    def get(self):
        email = self.request.get('email')
        print 'email: ', email
        user = users.User(email)
        auth_user = AuthorizedUser.gql("where user = :1", user).get()
        auth_user.delete()
        self.redirect('/auth/users')

def isauthorized():
    """ Returns True if the current user is authorized
    """
    user = users.get_current_user()
    if user:
        #logging.debug('Angemeldet als user  %s' % user.nickname())
        auth_user = AuthorizedUser.gql("where user = :1", user).get()
        if auth_user:
            return True
    return False
    
application = webapp.WSGIApplication([(r'/auth/?', ManageAuthorizedUsers),
                                      ('/auth/users', ManageAuthorizedUsers),
                                      ('/auth/useradd', ManageAuthorizedUsers),
                                      ('/auth/userdelete', DeleteAuthorizedUser)],
                                     debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
