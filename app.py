from flask import (Flask, redirect, url_for, session, request, 
                   render_template, Response)
from flask_oauth import OAuth
from flask.ext.bootstrap import Bootstrap
from flaskext.csrf import csrf
import redis
import json
import os

DEBUG = True if 'DEBUG' in os.environ else False
FACEBOOK_APP_ID = os.environ['FACEBOOK_APP_ID']
FACEBOOK_APP_SECRET = os.environ['FACEBOOK_APP_SECRET']
HACK_NAME = os.environ['HACK_NAME']
MYREDIS_URL = os.environ['MYREDIS_URL']
SECRET_KEY = os.environ['SECRET_KEY']
ADMIN_ID = os.environ['ADMIN_ID']

app = Flask(__name__)
Bootstrap(app)
csrf(app)
app.debug = DEBUG
app.secret_key = SECRET_KEY
oauth = OAuth()

facebook = oauth.remote_app('facebook',
    base_url='https://graph.facebook.com/',
    request_token_url=None,
    access_token_url='/oauth/access_token',
    authorize_url='https://www.facebook.com/dialog/oauth',
    consumer_key=FACEBOOK_APP_ID,
    consumer_secret=FACEBOOK_APP_SECRET,
    request_token_params={'scope': 
                          'user_likes,user_actions.music,user_actions.video'}
)


@app.route('/')
def index():
    return redirect(url_for('tos'))


def check_box(name, request):
    return name in request.form and request.form[name] == 'on'


@app.route('/tos', methods=['GET', 'POST'])
def tos():

    if request.method == 'GET':
        return render_template('tos.html', hack_name=HACK_NAME)

    if check_box('delete', request):
        return facebook.authorize(callback=url_for('delete', _external=True))
    elif check_box('ingress', request):
        return facebook.authorize(callback=url_for('ingress', _external=True))
    elif check_box('egress', request):
        return redirect(url_for('egress'))
    else:
        return redirect(url_for('index'))


@app.route('/ingress')
@facebook.authorized_handler
def ingress(resp):

    # Check response from facebook auth
    if resp is None:
        return render_template('message.html', title='Error', 
                               message=request.args['error_message'])

    # Get data from facebook
    session['oauth_token'] = (resp['access_token'], '')
    me = facebook.get(
        'me/?fields=name,likes,music.listens,video.watches,fitness.runs')

    # Add user data to store
    store = redis.StrictRedis.from_url(MYREDIS_URL)
    store.sadd(HACK_NAME, me.data['id'])
    store.set(me.data['id'], json.dumps(me.data))

    return redirect(request.args['next'])

@app.route('/egress')
def egress():

    # Get aggregate data from store
    store = redis.StrictRedis.from_url(MYREDIS_URL)
    members = store.smembers(HACK_NAME)
    member_data = store.mget(members) if members else []
    aggregate_data = '[' + ','.join(member_data) + ']'
    
    return Response(aggregate_data, mimetype='application/json') 


@app.route('/thanks')
def thanks():
    return render_template('message.html', title='Thanks',
                           message='Thank you for sharing your likes,\
listens, watches and runs with the %s hackers.' % HACK_NAME)


@app.route('/delete')
@facebook.authorized_handler
def delete(resp):

    # Check response from facebook auth
    if resp is None:
        return render_template('message.html', title='Error', 
                               message=request.args['error_message'])

    # Get data from facebook
    session['oauth_token'] = (resp['access_token'], '')
    me = facebook.get('me/?fields=id')

    # Check id
    if me.data['id'] != ADMIN_ID:
        return render_template('message.html', title='Error', 
                               message='Missing or invalid password')

    # Delete data
    store = redis.StrictRedis.from_url(MYREDIS_URL)
    members = store.smembers(HACK_NAME)
    store.delete(members)
    store.delete(HACK_NAME)

    return render_template('message.html', title='Deleted',
                           message='%s data deleted' % HACK_NAME)


@facebook.tokengetter
def get_facebook_oauth_token():
    return session.get('oauth_token')


if __name__ == '__main__':
    app.run()
