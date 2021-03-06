"""
This script initializes Geonode
"""

#########################################################
# Setting up the  context
#########################################################

import os, requests, json, uuid, django, time
django.setup()

#########################################################
# Imports
#########################################################

from django.core.management import call_command
from django.db import connection
from django.db.utils import OperationalError
from requests.exceptions import ConnectionError
from geonode.people.models import Profile
from oauth2_provider.models import Application
from django.conf import settings

# Getting the secrets
admin_username = os.getenv('ADMIN_USERNAME')
admin_password = os.getenv('ADMIN_PASSWORD')
admin_email = os.getenv('ADMIN_EMAIL')


#########################################################
# 1. Waiting for PostgreSQL
#########################################################

print("-----------------------------------------------------")
print("1. Waiting for PostgreSQL")
for _ in range(60):
    try:
        connection.ensure_connection()
        break
    except OperationalError:
        time.sleep(1)
else:
    connection.ensure_connection()
connection.close()

#########################################################
# 2. Running the migrations
#########################################################

print("-----------------------------------------------------")
print("2. Running the migrations")
call_command('migrate', '--noinput')


#########################################################
# 3. Creating superuser if it doesn't exist
#########################################################

print("-----------------------------------------------------")
print("3. Creating/updating superuser")
try:
    superuser = Profile.objects.get(username=admin_username)
    superuser.set_password(admin_password)
    superuser.is_active = True
    superuser.email = admin_email
    superuser.save()
    print('superuser successfully updated')
except Profile.DoesNotExist:
    superuser = Profile.objects.create_superuser(
        admin_username,
        admin_email,
        admin_password
    )
    print('superuser successfully created')


#########################################################
# 4. Create an OAuth2 provider to use authorisations keys
#########################################################

print("-----------------------------------------------------")
print("4. Create/update an OAuth2 provider to use authorisations keys")
app, created = Application.objects.get_or_create(
    pk=1,
    name='GeoServer',
    client_type='confidential',
    authorization_grant_type='authorization-code'
)
redirect_uris = [
    'http://{}/geoserver'.format(os.getenv('HTTPS_HOST',"") if os.getenv('HTTPS_HOST',"") != "" else os.getenv('HTTP_HOST')),
    'http://{}/geoserver/index.html'.format(os.getenv('HTTPS_HOST',"") if os.getenv('HTTPS_HOST',"") != "" else os.getenv('HTTP_HOST')),
]
app.redirect_uris = "\n".join(redirect_uris)
app.save()
if created:
    print('oauth2 provider successfully created')
else:
    print('oauth2 provider successfully updated')


#########################################################
# 5. Loading fixtures
#########################################################

print("-----------------------------------------------------")
print("5. Loading fixtures")
call_command('loaddata', 'initial_data')


#########################################################
# 6. Running updatemaplayerip
#########################################################

print("-----------------------------------------------------")
print("6. Running updatemaplayerip")
# call_command('updatelayers') # TODO CRITICAL : this overrides the layer thumbnail of existing layers even if unchanged !!!
call_command('updatemaplayerip')


#########################################################
# 7. Collecting static files
#########################################################

print("-----------------------------------------------------")
print("7. Collecting static files")
call_command('collectstatic', '--noinput', verbosity=0)

#########################################################
# 8. Waiting for GeoServer
#########################################################

print("-----------------------------------------------------")
print("8. Waiting for GeoServer")
for _ in range(60*5):
    try:
        requests.head("http://geoserver:8080/geoserver")
        break
    except ConnectionError:
        time.sleep(1)
else:
    requests.head("http://geoserver:8080/geoserver")

#########################################################
# 9. Securing GeoServer
#########################################################

print("-----------------------------------------------------")
print("9. Securing GeoServer")

# Getting the old password
try:
    r1 = requests.get('http://geoserver:8080/geoserver/rest/security/masterpw.json', auth=(admin_username, admin_password))
except requests.exceptions.ConnectionError as e:
    print("Unable to connect to GeoServer. Make sure GeoServer is started and accessible.")
    exit(1)
r1.raise_for_status()
old_password = json.loads(r1.text)["oldMasterPassword"]

if old_password=='M(cqp{V1':
    print("Randomizing master password")
    new_password = uuid.uuid4().hex
    data = json.dumps({"oldMasterPassword":old_password,"newMasterPassword":new_password})
    r2 = requests.put('http://geoserver:8080/geoserver/rest/security/masterpw.json', data=data, headers={'Content-Type': 'application/json'}, auth=(admin_username, admin_password))
    r2.raise_for_status()
else:
    print("Master password was already changed. No changes made.")
