"""
Simple flask application that emulates how twitter behaves.
It takes as input a directory where it will find a small number of user
profiles from which to load information
"""

from flask import *
from twitter.settings import LOOKUP_DATABASE, LOOKUP_PORT, LOOKUP_URL

app = Flask(__name__)

dataset_timeline = {}
dataset_followers = {}

DEBUG = True

import os
import sys
import json
import gzip
import glob
import time

def load_dataset_from(directory):
    print "Loading data from", directory

    for count, filename in enumerate(glob.glob(os.path.join(directory, '*/*'))):
        try:
            user_id = int(os.path.basename(filename)[:-4])
        except:
            continue

        dataset = None
        global dataset_timeline
        global dataset_followers
        
        if filename.endswith('.twt'):
            dataset = dataset_timeline
        elif filename.endswith('.fws'):
            dataset = dataset_followers

        if dataset is not None:
            try:
                with gzip.open(filename, 'r') as input:
                    data = input.readlines()
                    dataset[user_id] = data

                print "File %s loaded" % filename
            except:
                print "Error loading", filename

    print "Dataset successfully loaded. %d files loaded." % count

def get_timeline(user_id, max_id=-1, since_id=-1):
    response = []
    for line in dataset_timeline[user_id]:
        tweet = json.loads(line)
        if max_id == -1 and since_id == -1:
            response.append(tweet)
        else:
            if max_id != -1 and int(tweet['id_str']) <= max_id:
                response.append(tweet)
            if since_id != -1 and int(tweet['id_str']) > since_id:
                response.append(tweet)
        if len(response) >= 200:
            break

    return response

def get_followers(user_id, cursor=0):
    response = []
    print user_id in dataset_followers

    for count, line in enumerate(dataset_followers[user_id]):
        if len(response) >= 10:
            break
        if count >= cursor:
            response.append(line.strip())

    if count == len(dataset_followers[user_id]) - 1:
        count = 0

    return {'ids': response, 'next_cursor_str': count}

remaining = 1

def set_rate(response):
    global remaining

    response.headers['x-ratelimit-remaining'] = remaining
    response.headers['x-ratelimit-reset'] = time.time() + 2
    remaining -= 1

    if remaining == 0:
        response.data = json.dumps([])
        remaining = 10

    return response

@app.route('/1.1/statuses/user_timeline.json')
def lookup_by_userid():
    max_id = request.args.get('max_id', '')
    since_id = request.args.get('since_id', '')
    user_id = request.args.get('user_id', '')

    # TODO: Aggiungi restrizioni su IP

    try:
        since_id = int(since_id)
    except:
        since_id = -1

    try:
        max_id = int(max_id)
    except:
        max_id = -1

    if not user_id:
        return Response('', status=404, mimetype='application/json')

    try:
        data = get_timeline(int(user_id), max_id, since_id)
        return set_rate(Response(json.dumps(data), status=200, mimetype='application/json'))
    except KeyError:
        return set_rate(Response('', status=404, mimetype='application/json'))

@app.route('/1.1/followers/ids.json')
def get_followers_ids():
    user_id = request.args.get('user_id', '')
    cursor  = request.args.get('cursor', '')

    try:
        cursor = int(cursor)
    except:
        cursor = 0

    try:
        data = get_followers(int(user_id), cursor)
        return set_rate(Response(json.dumps(data), status=200, mimetype='application/json'))
    except KeyError:
        return set_rate(Response('', status=404, mimetype='application/json'))

@app.route('/1.1/users/lookup.json', methods=['POST'])
def lookup_users():
    lookup = []
    user_ids = request.form.get('user_id', '')

    for user_id in user_ids.split(','):
        # Randomly generate a lookup information
        lookup.append({
            'lang': 'en',
            'statuses_count': 200,
            'screen_name': 'testing',
            'id_str': user_id
        })

    return set_rate(Response(json.dumps(lookup), status=200, mimetype='application/json'))


if __name__ == '__main__':
    load_dataset_from(sys.argv[1])
    app.run(debug=True)