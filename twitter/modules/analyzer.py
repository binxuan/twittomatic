import json
from twitter import settings
from twitter.const import *
from twitter.modules import TwitterResponse, fileutils, fetcher
from twisted.python import log

LOOKUP_URL = settings.TWITTER_URL + "users/lookup.json"

class FollowerReader(object):
    """
    Please note that in this file line numbers are considered to start from 0
    although the warning expose to the user a warning with line+1 just to be
    informative
    """
    def __init__(self, file, filename, start_line=0):
        self.file = file
        self.filename = filename
        self.start_line = start_line
        self.follower_count = 0

        lineno = 0
        set_position = None
        iterable = iter(self.file)

        while True:
            try:
                position = self.file.tell()
                line = iterable.next()
                lineno += 1

                if lineno >= start_line and set_position is None:
                    set_position = position

                if line.strip():
                    try:
                        int(line.strip())
                        self.follower_count += 1
                    except:
                        pass

            except StopIteration:
                break

        if set_position is not None:
            self.file.seek(set_position, 0)

        del iterable
        self.iterable = iter(self.file)
        self.current_line = 0

    def get_followers(self):
        for lineoff, line in enumerate(self.iterable):
            if not line or not line.strip():
                continue

            lineoff += self.start_line
            self.current_line = lineoff
            follower_id = None

            try:
                follower_id = int(line.strip())
            except:
                log.msg("Error in file %s at line %d: %s is not convertible to a user_id" % \
                    (self.filename, self.current_line + 1, line.strip()))

            if follower_id is not None:
                yield (self.current_line, follower_id)

    def __str__(self):
        return "FollowerReader: %s start line: %d current line: %d" % \
            (self.filename, self.start_line, self.current_line)


def analyze_followers(reader, already_processed=lambda x: False, progress_cb=lambda x: None, max_requests=-1):
    """
    Analyze a list of followers contained in a given file.
    @param reader is an instance of FollowerReader
    @param already_processed is a function that takes in input an user_id and
           returns True in case the user is going to be processed or it is
           already processed.
    """

    assert isinstance(reader, FollowerReader)
    assert reader.follower_count > 0

    count = 0
    batch = []
    lookup_infos = []
    iterable = reader.get_followers()

    while True:
        consumed = False

        while len(batch) < BATCH_LIMIT:
            try:
                _, follower_id = iterable.next()
            except StopIteration:
                consumed = True
                break

            if not already_processed(follower_id):
                batch.append(follower_id)

        users = ','.join(map(str, batch))
        payload = {
            'include_entities': 'f',
            'user_id': users,
        }

        try:
            count += 1
            r, collection, msg, sleep_time = fetcher.fetch_url('post', LOOKUP_URL, data=payload, log_request=False)
        except fetcher.TooManyAttemptsException:
            return (MSG_BAN, lookup_infos, 60)

        print collection
        print r.content

        if msg == MSG_OK:
            batch = []
            lookup_infos.extend(collection)
            progress_cb(lookup_infos)
            # Jump below
        else:
            return (msg, lookup_infos, sleep_time)

        if max_requests > 0 and count >= max_requests:
            return (msg, lookup_infos, sleep_time)

        if consumed:
            return (msg, lookup_infos, sleep_time)

def analyze_followers_of(user_id, start_line=0,
                         already_processed=lambda x: False,
                         must_follow=lambda x: True):

    with fileutils.open_file(user_id, 'fws', mode=fileutils.READ) as status:
        file, stats = status
        reader = FollowerReader(file, str(user_id) + '.fws', start_line)

        def log_progress(lookup_infos):
            log.msg("Follower of user_id %d: analyzed %d of %d [%02d%%]" % \
                    (user_id, len(lookup_infos), reader.follower_count,
                     100 * (len(lookup_infos) / float(reader.follower_count))))

        msg, lookup_infos, sleep_time = analyze_followers(
            reader, already_processed=already_processed,
            progress_cb=log_progress
        )

        included = []

        for info in lookup_infos:
            if must_follow(info):
                included.append(info['id_str'])

        total_included = len(included)
        total_fetched = len(lookup_infos)

        response = TwitterResponse(TwitterResponse.msg_to_status(msg),
            user_id,
            reader.current_line + 1, # We advance the state also if there's an error. Master has to catch this
            sleep_time
        )

        response['analyzer.total_included'] = total_included
        response['analyzer.total_fetched'] = total_fetched
        response['analyzer.target_users'] = included

        return response


if __name__ == "__main__":
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option("-n", "--number", dest="number", type="int", default=1,
                      help="Limit the number of requests (default: 1)")
    parser.add_option("-f", "--file", dest="filename",
                      help="followers file of the target user", metavar="FILE")
    parser.add_option("-e", "--expression", dest="expression", default="id_str,screen_name",
                  help="print out only a specific portion of the JSON (default: id_str,screen_name)")

    (options, args) = parser.parse_args()

    if options.filename:
        with open(options.filename, 'r') as infile:
            reader = FollowerReader(infile)
            msg, lookup_infos, sleep_time = analyze_followers(
                reader,
                max_requests=options.number
            )

        for info in sorted(lookup_infos):
            if options.expression:
                result = []

                for subexpr in options.expression.split(','):
                    obj = info
                    for param in subexpr.split('/'):
                        obj = obj.get(param, '')
                    result.append(unicode(obj))

                print ('\t'.join(result)).encode('utf8')
            else:
                print info
    else:
        parser.print_help()