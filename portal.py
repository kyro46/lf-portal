# -*- coding: utf-8 -*-
"""
	Flaskr
	~~~~~~

	A microblog example application written as Flask tutorial with
	Flask and sqlite3.

	:copyright: (c) 2010 by Armin Ronacher.
	:license: BSD, see LICENSE for more details.
"""
from functools import wraps
from flask import Flask, request, session, g, redirect, url_for, abort, \
		render_template, flash, _app_ctx_stack
import urllib
import urllib2
from xml.dom.minidom import parseString
import random
try:
	import pylibmc
except ImportError:
	import memcache

# Configuration -----------------------------------------------------
SEARCH_SERVICE   = 'http://engage.opencast.org/search/'
SECURITY_SERVICE = 'http://engage.opencast.org/j_spring_security_check'
SECRET_KEY       = 'development key'
SERIES_PER_PAGE  = 50

# One of: simple, track-url, included
#   simple    Try to construct the player URL by ENGAGE_SERVICE variable and
#             mediapackage id. Fast but reliable only in some cases. Not if
#             there are more than one engage server and not if the IDs might
#             have changed.
#   track-url Try to construct the engage player URL from a random track URL.
#             This will work in most cases. Even if there are more than one
#             engage server. Not, however, if the tracks are served from a
#             dedicated server which is not the engage server.
#   included  Uses the links included in the mediapackage. This is the most
#             reliable one. But this method only works if the links to the
#             player are included into the mediapackage.
ENGAGE_URL_DETECTION = 'track-url'

# Set this if ENGAGE_URL_DETECTION is set to simple:
#ENGAGE_SERVICE   = 'http://engage.opencast.org/engage/'

# Set this if ENGAGE_URL_DETECTION is set to track-url:
# The following value specifies the position of the mediapackage identifier in
# a track URL, if split by '/':
TRACK_ID_PART = 5


USE_MEMCACHD     = True
MEMCACHED_HOST   = 'localhost:11211'
CACHE_TIME_SEC   = 600

# Configuration for built-in server only:
SERVER_DEBUG = True
SERVER_HOST  = '0.0.0.0' # Set to localhost for local access only
SERVER_PORT  = 5000
# Configuration end -------------------------------------------------


# Create application :)
app = Flask(__name__)
app.config.from_object(__name__)


def get_mc():
	'''Returns a Memcached client. If there is none for the current application
	context it will create a new.
	'''
	top = _app_ctx_stack.top
	if not hasattr(top, 'memcached_cli'):
		try:
			top.memcached_cli = pylibmc.Client(
					[app.config['MEMCACHED_HOST']], binary = True,
					behaviors = {'tcp_nodelay': True, 'ketama': True})
		except NameError:
			top.memcached_cli = memcache.Client(
					[app.config['MEMCACHED_HOST']], debug=0)
	return top.memcached_cli


def cached(time=app.config['CACHE_TIME_SEC']):
	'''Mark a method as to be cached. The optional argument 'time' specifies how
	long the data should be cached. The default is the value of the
	configuration variable 'CACHE_TIME_SEC'.
	'''
	def decorator(f):
		@wraps(f)
		def decorated(*args, **kwargs):
			if not app.config['USE_MEMCACHD']:
				return f(*args, **kwargs)
			mc = get_mc()
			key = 'lf_portal_' + request.url \
					+ str(request.cookies.get('JSESSIONID'))
			result = mc.get(key)
			if not result:
				result = f(*args, **kwargs)
				mc.set(key, result, time)
			return result
		return decorated
	return decorator


def request_data(what, limit, offset, id=None, sid=None, q=None):
	'''Request data from the Matterhorn Search service.

	:param what:   Type of data to request (series or episode).
	:param limit:  The maximum amount of results to request.
	:param offset: The offset of the first value to request.
	:param id:     The id of the objects to request.
	:param sid:    The series id of the objects to return (episodes only).
	:param q:      A freetext search request.
	'''
	url  = '%s%s.xml?limit=%i&offset=%i' % \
			( app.config['SEARCH_SERVICE'], what, limit, offset )
	if id:
		url += '&id=%s' % id
	if sid:
		url += '&sid=%s' % sid
	if q:
		url += '&q=%s' % q
	req  = urllib2.Request(url)
	
	cookie = request.cookies.get('JSESSIONID')
	if cookie:
		req.add_header('cookie', 'session="%s"; Path=/; HttpOnly' % cookie)

	req.add_header('Accept', 'application/xml')
	u = urllib2.urlopen(req)
	try:
		data = parseString(u.read())
	finally:
		u.close()
	return data


def get_xml_val(elem, name):
	'''Get a specific value from an XML structure.

	:param elem: Root element of the XML element to search in.
	:param name: Name of the element which should be returned.
	'''
	try:
		return elem.getElementsByTagNameNS('*', name)[0].childNodes[0].data
	except IndexError:
		return ''


def prepare_episode(data):
	'''Prepare a episode result XML for further usage. In other words: Extract
	all necessary and wanted  values and put them into a dictionary.

	:param data: XML structure containing the data.
	'''
	episodes = []
	for media in data.getElementsByTagNameNS('*', 'mediapackage'):
		id = media.getAttribute('id')
		title       = get_xml_val(media, 'title')
		series      = get_xml_val(media, 'series')
		seriestitle = get_xml_val(media, 'seriestitle')
		img = None

		player = None
		if app.config['ENGAGE_URL_DETECTION'] == 'simple':
			player = '%sui/watch.html?id=%s' % (app.config['ENGAGE_SERVICE'], id)
		elif app.config['ENGAGE_URL_DETECTION'] == 'track-url':
			for track in media.getElementsByTagNameNS('*', 'track'):
				for url in track.getElementsByTagNameNS('*', 'url'):
					url = url.childNodes[0].data
					if not url.startswith('http'):
						continue
					url = url.split('/')
					player = '%s/engage/ui/watch.html?id=%s' % (
							'/'.join(url[:3]), 
							url[app.config['TRACK_ID_PART']] )
		elif app.config['ENGAGE_URL_DETECTION'] == 'included':
			print 'TODO: Implement this'

		for attachment in media.getElementsByTagNameNS('*', 'attachment'):
			if attachment.getAttribute('type').endswith('/player+preview'):
				img = attachment.getElementsByTagNameNS('*', 'url')[0].childNodes[0].data


		episodes.append( {'id':id, 'title':title, 'series':series,
			'seriestitle':seriestitle, 'img':img, 'player':player} )
	return episodes


def prepare_series(data):
	'''Prepare a series result XML for further usage. In other words: Extract
	all necessary and wanted  values and put them into a dictionary.

	:param data: XML structure containing the data.
	'''
	series = []
	for result in data.getElementsByTagNameNS('*', 'result'):
		if get_xml_val(result, 'mediaType') != 'Series':
			continue
		id = result.getAttribute('id')
		title       = get_xml_val(result, 'dcTitle')
		description = get_xml_val(result, 'dcDescription')

		creator     = [ c.childNodes[0].data 
				for c in result.getElementsByTagNameNS('*', 'dcCreator') ]

		contributor = [ c.childNodes[0].data 
				for c in result.getElementsByTagNameNS('*', 'dcContributor') ]

		series.append( {'id':id, 'title':title, 'creator':creator,
			'contributor':contributor} )
	return series


@app.route('/')
@cached(20)
def home():
	'''Render home page:

	- Get the six latest recordings
	- Get another six random recordings
	
	This method is cached for only 20 seconds. This should help under heavy load.
	But the random picks will probably be different the next time a single user
	visits the page.
	'''
	data = request_data('episode',6,0)
	total = data.getElementsByTagNameNS('*', 'search-results')[0].getAttribute('total')
	new_episodes = prepare_episode(data)

	# get some random picks
	# random.seed()
	offsets = [x+1 for x in random.sample(xrange(int(total)), 6)]
	random_episodes = []
	for offset in offsets:
		data = request_data('episode',1,offset)
		random_episodes += prepare_episode(data)

	return render_template('home.html', new_episodes=new_episodes,
			random_episodes=random_episodes)


@app.route('/lectures')
@app.route('/lectures/<int:page>')
@cached()
def lectures(page=1):
	'''Renders the lectures page which displays a list of all available series.

	This method is awfully slow and puts some stress on the server if used with
	Matterhorn 1.3.1 due to some bugs in the Matterhorn Search service.
	
	The caching of this method minimizes the effect of this bug, however.
	'''
	page -= 1

	data = request_data('series', app.config['SERIES_PER_PAGE'], 
			app.config['SERIES_PER_PAGE'] * page)
	total = data.getElementsByTagNameNS('*', 'search-results')[0].getAttribute('total')
	series = prepare_series(data)

	pages = [ p+1 for p in xrange(int(total) / app.config['SERIES_PER_PAGE']) ]
	return render_template('lectures.html', series=series, pages=pages, activepage=page)


@app.route('/episode/<id>')
def episode(id):
	'''Renders the page which shows a single episode. This page is not cached to
	prevent the cache from being filled with pages that are not so frequently
	viewed.

	:param id: Specifies the identifier of a single episode.
	'''
	data    = request_data('episode', 1, 0, id=id)
	episode = prepare_episode(data)
	episode = episode[0] if episode else None
	return render_template('episode.html', episode=episode)


@app.route('/series/<id>')
@cached()
def series(id):
	'''Renders the page for a single series. The page will display the title,
	the creators and contributors and a list of all recordings which belong to
	one series.

	NOTICE: There seems to be a bug in 1.3.1 (also 1.4?) which prevents the
	search endpoint to return the episodes of a series under some mysterious
	circumstances.

	:param id: Specifies the identifier of a single series.
	'''
	data     = request_data('series', 1, 0, id=id)
	series   = prepare_series(data)
	series   = series[0] if series else None

	data     = request_data('episode', 999, 0, sid=series.get('id'))
	episodes = prepare_episode(data)

	return render_template('series.html', series=series, episodes=episodes)


@app.route('/search')
@app.route('/search/<int:page>')
@cached()
def search(page=1):
	'''Renders the search page. Series results will be displayed at the top of
	the first page. Episode results will be paged. Each page contains nine
	episode results.
	'''
	page -= 1
	q     = request.args.get('q')

	series = []
	if not page:
		data     = request_data('series', 9999, 0, q=q)
		series   = prepare_series(data)

	data     = request_data('episode', 9, 0, q=q)
	total    = data.getElementsByTagNameNS('*', 'search-results')[0].getAttribute('total')
	episodes = prepare_episode(data)

	pages = [ p+1 for p in xrange(int(total) / 9) ]

	return render_template('search.html', series=series, episodes=episodes,
			pages=pages, activepage=page)


class NoRedirection(urllib2.HTTPErrorProcessor):
	'''This handler will prevent httplib2 from following redirections.
	'''
	def http_response(self, request, response):
		return response

	https_response = http_response


@app.route('/login', methods=['GET', 'POST'])
def login():
	'''Login to Matterhorn. This method will request the Matterhorn Login page
	to obtain a session which can be used for further requests.
	'''
	error = None
	if request.method == 'POST':
		# Prepare data
		data = {
				'j_username': request.form['username'],
				'j_password': request.form['password'] }
		try:
			opener = urllib2.build_opener(NoRedirection)
			u = opener.open(app.config['SECURITY_SERVICE'],
					urllib.urlencode(data))
			if '/login.html' in u.headers.get('location'):
				return render_template('login.html',
						error='Could not log in. Incorrect credentials?')
			cookie = u.headers.get('Set-Cookie')
			u.close()

			response = redirect(url_for('home'))
			response.headers['Set-Cookie'] = cookie
			return response

		except urllib2.HTTPError as e:
			if e.code == 404:
				return render_template('login.html',
						error='Login service returned error. Please report this.')
			if e.code == 401:
				return render_template('login.html',
						error='Could not log in. Incorrect credentials?')
			raise e

	return render_template('login.html')


@app.route('/logout')
def logout():
	'''This will delete the cookie containing the session id for Matterhorn
	authentication.
	'''
	response = redirect(url_for('home'))
	response.headers['Set-Cookie'] = 'JSESSIONID=x; Expires=Wed, 09 Jun 1980 10:18:14 GMT'
	return response


if __name__ == '__main__':
	app.run(host=SERVER_HOST, port=SERVER_PORT, debug=SERVER_DEBUG)