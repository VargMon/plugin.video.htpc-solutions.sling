from ConfigParser import ConfigParser

import collections
import HTPCSolutions
import json
import operator
import subprocess
import sys
import xbmc, xbmcaddon

####################################################################################################

addon = xbmcaddon.Addon()
config = ConfigParser()
db = HTPCSolutions.DB()
http = HTPCSolutions.HTTP()
parameters = HTPCSolutions.Parameters()
settings = HTPCSolutions.Settings()
ui = HTPCSolutions.UI()
where = HTPCSolutions.where

####################################################################################################

class Auth(HTPCSolutions.Auth):

	def validate(self):
		
		if self.hasCredentials == True:
			for i in range(2):
				data = self.http.url("https://accounts.sling.com/accounts/sling/login/loginForm", {
					'emailAddress': self.username,
					'password': self.password
				})

			if data == None:
				self.debug("No data was return from server", xbmc.LOGERROR)
				return False

			if not data.find('<a href="/accounts/member/logout">Log out</a>') == -1:
				self.authenticated = True
				return True
			else:
				self.authenticated = False
				return False

		return False

####################################################################################################

class Main(HTPCSolutions.Debug):

	def __init__(self):

		self.auth = Auth()

		if self.auth.hasCredentials == False:
			ui.dialog("Credentials", "Please enter your Sling username and password before continuing.")
			settings.open()

		if parameters.count() < 1:
			self.debug("action is default")
			self.list()
		
		elif parameters.has("mode") and parameters.has("action"):	

			mode = parameters.get("mode")
			action = parameters.get("action")
			
			self.debug( "mode {0} - action {1}".format(mode, action) )

			if mode == "client" and action == "launch":
				Client().launch()
			elif mode == "boxes" and action == 'default':
				Boxes().default()
			elif mode == "boxes" and action == 'update':
				Boxes().update()
			elif mode == "live" and action == "channels":
				Live().channels()
			elif mode == "live" and action == "genres":
				Live().genres()
			elif mode == "live" and action == "integrate":
				Live().integrate()
			elif mode == "live" and action == "update":
				Live().update()
			elif mode == "settings" and action == "clear":
				settings.clear()
			elif mode == "settings" and action == "open":
				settings.open()
			elif mode == "settings" and action == "set":
				settings.set(parameters.get("name"), parameters.get("value"))
				self.notify("Settings Updated")
			else:
				self.debug("Nice try, I don't support this mode/action")

		else:
			
			self.ui.end(False)


	def list(self):
		ui.add("Live TV", "live", "channels", image=None, isFolder=True)
		ui.add("Genres", "live", "genres", image=None, isFolder=True)
		ui.add("Boxes", "boxes", "default", image=None, isFolder=True)
		ui.add("Quick Connect", "client", "launch", image=None, isFolder=False)
		ui.add("Settings", "settings", "open", image=None, isFolder=False)
		ui.end()

####################################################################################################

class Boxes(HTPCSolutions.Debug):

	url = "https://newwatchsecure.slingbox.com/watch/slingAccounts/account_boxes_js"

	def __init__(self):
		super(Boxes, self).__init__()
		
		self.auth = Auth()
		self._boxes = db.table('boxes')

	@property
	def count(self):
		return len(self._boxes)

	def default(self, name=None, value=None):
		for box in self._boxes.all():
			ui.add(box["name"], "settings", "set", image=None, isFolder=False, params = { "name": "box.default", "value": box["id"] } ) 
		ui.end()

	def get(self):
		if self.count > 0:
			for i in self._boxes.all():
				return i
		else:
			return None

	def update(self):
		
		self.notify("Update Starting")

		if self.auth.hasCredentials == False:
			self.notify("Can't perform update without credentials")
			return False
		
		self.auth.validate()
		if self.auth.authenticated == False:
			self.notify("Authentication Failed")
			return False
		else:
			self.notify("Authentication Successful")

		# Get List Of Boxes
		http.cookies.load()
		http.cookies.set(name="slingboxLocale", value="en_uk", domain="slingbox.com", path="/", version=0)
		
		self.debug(http.cookies._jar)
		data = http.url(Boxes.url)
		self.debug(data)
		self.debug(http.cookies._jar)
		
		# check to ensure data was returned
		if not data:
			self.notify("Update Failed - No Data From Server")
			self.debug("No data was return from the server", xbmc.LOGERROR)
			return False

		# Check to see if we've received anything.
		if (data == ""):
			self.notify("Update Failed -JSON is invalid")
			debug("%s - JSON is invalid" % (__name__))
			return False
		
		# replace invalid json information
		data = json.loads(data.replace("var sling_account_boxes=",""))

		# Remove all exisiting records
		self._boxes.remove()

		# Enumerate JSON Category
		for item in data['memberslingbox']:
			box = data['memberslingbox'][item]
			self._boxes.insert({
				'name': box['displayName'],
				'finderId': box['finderId'],
				'id': item,
				'username': 'admin',
				'password': box['adminPassword']
			})

		self.notify("Update Completed")

####################################################################################################

class Client(HTPCSolutions.Debug):

	def __init__(self):
		super(Client, self).__init__()
		
		self.auth = Auth()
		self.boxes = Boxes()
		self.executable = xbmc.translatePath(addon.getAddonInfo('path') + "/resources/bin/client.exe").decode('utf-8')
		self.process = None

	def launch(self, mode = "live", **kwargs):

		if self.auth.hasCredentials == True and self.boxes.count == 0:
			self.boxes.update()
		
		box = self.boxes.get()

		if box == None:
			return

		arguments = [
			self.executable,
			"--username", box['username'],
			"--password", box['password'],
			"--finderid", box['finderId'],
			"--debug-enabled", settings.get('debug.enabled')
		]

		if parameters.has('number'):
			arguments.extend(["--channel", parameters.get('number')])

		self.debug(arguments)

		self._process = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
	
####################################################################################################

class Live(HTPCSolutions.Debug):

	tvguide = xbmc.translatePath("special://home/addons/script.tvguide/resources/addons.ini")
	url = "http://epgservices.sky.com/tvlistings-proxy/TVListingsProxy/init.json?siteId=1"

	def __init__(self):

		super(Live, self).__init__()

		self._channels = db.table('channels')
		self._genres = db.table('genres')

	def channels(self):
		
		if parameters.has("genre"):
			channels = self._channels.search(where('genre') == parameters.get("genre"))
		else:
			channels = self._channels.all()

		# for i in sorted(self.configuration._json, key=operator.itemgetter(0)):
		for channel in channels:
			ui.add(channel["name"], "client", "launch", image=channel["thumb"], isFolder=False, params = dict(channel) )
		ui.end()

	def genres(self, name=None, value=None):

		for genre in self._genres.all():
			ui.add(genre["name"], "live", "channels", image=genre["thumb"], isFolder=True, params = { 'genre': genre["id"] }) 
		ui.end()

	def integrate(self):

		self.debug("Integrating with TVGuide Addon")
		
		config.read(Live.tvguide)

		if config.has_section(addon.getAddonInfo('id')):
			config.remove_section(addon.getAddonInfo('id'))

		config.add_section(addon.getAddonInfo('id'))

		for channel in self._channels.all():
			config.set(addon.getAddonInfo('id'), channel['name'], "plugin://%s/?mode=client&action=launch&id=%s" % ( addon.getAddonInfo('id'), channel['id'] ) )

		with open(xbmc.translatePath('special://home/addons/script.tvguide/resources/addons.ini'), 'wb') as configfile:
			config.write(configfile)

	def update(self):
		
		self.notify("Update Starting")

		# Get List Of Channels
		data = http.json(Live.url)

		# check to ensure data was returned
		if not data:
			self.notify("Update Failed - No Data From Server")
			self.debug("No data was return from the server", xbmc.LOGERROR)
			return False

		# Check to see if we've received anything.
		if ((data == "") or (data.has_key('channels') == False)):
			self.notify("Update Failed -JSON is invalid")
			debug("%s - JSON is invalid" % (__name__))
			return False
		
		# Remove all exisiting records
		self._channels.remove()
		self._genres.remove()

		# Enumerate JSON Category
		for item in data['channels']:
			self._channels.insert({
				'genre': item['genre'],
				'id': item['channelid'],
				'number': item['channelno'],
				'name': item['title'],
				'thumb': ('http://epgstatic.sky.com/epgdata/1.0/newchanlogos/500/500/skychb%s.png' % item['channelid']),
				'type': item['channeltype']
			})

		# Enumerate JSON Category
		for item in data['genre']:
			self._genres.insert({
				'id': item['genreid'],
				'name': item['name'],
				'thumb': ''
			})

		self.notify("Update Completed")

####################################################################################################

if __name__ == "__main__":
	Main()
