import pprint
import sys
import ConfigParser
import pdb
import requests
import simplejson as json
from invdns.options import *

pp = pprint.PrettyPrinter(indent=4)
auth=None
API_MAJOR_VERSION = 1
CONFIG_FILE = "./config.cfg"

config = ConfigParser.ConfigParser()
config.read(CONFIG_FILE)

host = config.get('remote','host')
port = config.get('remote','port')
REMOTE = "http://{0}:{1}".format(host, port)

class InvalidCommand(Exception):
    pass


def dispatch(nas):
    if nas.rdtype == 'search':
        return dispatch_search(nas)
    if nas.rdtype == 'NS':
        return dispatch_NS(nas)
    if nas.rdtype == 'A':
        return dispatch_A(nas)
    if nas.rdtype == 'AAAA':
        return dispatch_AAAA(nas)

def dispatch_NS(nas):
    pass

def dispatch_MX(nas):
    pass

def dispatch_AAAA(nas):
    data = {}
    if nas.action == 'create':
        data['ip_type'] = '6'
    return _dispatch_addr_record(nas, data)

def dispatch_A(nas):
    data = {}
    if nas.action == 'create':
        data['ip_type'] = '4'
    return _dispatch_addr_record(nas, data)

class Dispatch(object):
    object_url = "/mozdns/api/v{0}_dns/{1}/{2}/"
    object_list_url = "/mozdns/api/v{0}_dns/{1}/"

    def handle_resp(self, nas, data, resp):
        resp_msg = self.get_resp_text(resp)
        if resp.status_code == 404:
            if nas.format == 'text':
                print "http_status: 404"
            else:
                self.error_out(nas, data, resp)
        elif resp.status_code == 500:
            print "SERVER ERROR! (Please email this output to a code monkey)"
            self.error_out(data, resp)
        elif resp.status_code == 400:
            # Bad Request
            if nas.format == 'json':
                print resp_msg
            elif nas.format in ('text', 'bind'):
                if 'error_messages' in resp_msg:
                    print self.get_errors(resp_msg['error_messages'])
            return 1
        elif resp.status_code == 201:
            # Created
            if nas.format == 'text':
                print "http_status: 201 (Created)"
                for k, v in resp_msg.iteritems():
                    print "{0}: {1}".format(k, v)
            if nas.format == 'json':
                print resp_msg
            return 0
        elif resp.status_code == 202:
            # Accepted
            if nas.format == 'text':
                print "http_status: 202 (Accepted)"
                for k, v in resp_msg.iteritems():
                    print "{0}: {1}".format(k, v)
            if nas.format == 'json':
                print resp_msg
            return 0
        elif resp.status_code == 200:
            # Success
            if nas.format == 'text':
                print "http_status: 200 (Success)"
                for k, v in resp_msg.iteritems():
                    print "{0}: {1}".format(k, v)
            if nas.format == 'json':
                print resp_msg
            return 0
        else:
            print "Client didn't understand the response."
            print "CLIENT ERROR! (Please email this output to a code monkey)"
            self.error_out(nas, data, resp)
            return 1

    def get_errors(self, resp_msg):
        messages = json.loads(resp_msg)
        errors = ''
        for error, msg in messages.iteritems():
            if error == '__all__':
                error = "Object Error"
            errors += "Error: {0}  {1}".format(error, ', '.join(msg))
        return errors

    def get_resp_text(self, resp):
        if resp.text:
            # Tasty pie returns json that is unicode. Thats ok.
            msg = json.loads(resp.text, 'unicode')
            return msg
        return 'No message from server'

    def error_out(self, nas, data, resp):
        print nas
        print data
        pprint.pprint(vars(resp))
        return 1



class ActionDispatch(Dispatch):
    def delete(self):
        pass

    def detail(self, nas):
        url = self.object_url.format(API_MAJOR_VERSION,
                                          self.resource_name, nas.pk)
        url = "{0}{1}?format=json".format(REMOTE, url)
        headers = {'content-type': 'application/json'}
        resp = requests.get(url, headers=headers, auth=auth)
        return self.handle_resp(nas, {}, resp)

    def update(self, nas):
        data = self.get_update_data()  # Dispatch defined Hook
        tmp_url = object_url.format(API_MAJOR_VERSION, self.resource_name,
                                    nas.pk)
        url = "{0}{1}".format(REMOTE, tmp_url)
        return self.action(url, requests.patch, data)

    def create(self, nas):
        data = self.get_create_data()  # Dispatch defined Hook
        tmp_url = object_list_url.format(API_MAJOR_VERSION, self.resource_name)
        url = "{0}{1}".format(REMOTE, tmp_url)
        return self.action(url, requests.post, data)

    def action(self, url, method, data):
        headers = {'content-type': 'application/json'}
        data = json.dumps(data)
        resp = method(url, headers=headers, data=data, auth=auth)
        self.handle_resp(nas, data, resp)
        return data

    def get_create_data():
        data = {}
        for add_arg, extract_arg in self.create_args:
            data.update(extract_arg())
        return data


    def get_update_data():
        data = {}
        for add_arg, extract_arg in self.update_args:
            data.update(extract_arg())
        return data

class SearchDispatch(Dispatch):

    def search(nas):
        """This is the fast display minimal information search. Use the
        object_search to get a more detailed view of a specific type of object.
        """
        tmp_url = "/core/search/search_dns_text/"
        url = "{0}{1}".format(REMOTE, tmp_url)
        headers = {'content-type': 'application/json'}
        search = {'search': nas.query}
        resp = requests.get(url, params=search, headers=headers, auth=auth)
        if resp.status_code == 500:
            print "CLIENT ERROR! (Please email this output to a code monkey)"
            error_out(nas, search, resp)
            return
        print resp.text

dispatches.append(SearchDispatch())




dispatches = []  # This global is where Dispatch classes register to signify that
                 # they need a parser built for them.

def build_dns_parsers(base_parser):
    for dispatch in dispatches:
        record_base_parser = base_parser.add_parser(dispatch.dtype, help="The"
                " interface for {0} records".format(dispatch.dtype),
                add_help=True)
        action_parser = record_base_parser.add_subparsers(help="{0} record "
                    "actions".format(dispatch.dtype), dest='action')
        build_create_parser(dispatch, action_parser)
        build_update_parser(dispatch, action_parser)
        build_delete_parser(dispatch, action_parser)
        build_detail_parser(dispatch, action_parser)

def build_create_parser(dispatch, action_parser):
    create_parser = action_parser.add_parser('create', help="Create "
                        "a(n) {0} record".format(dispatch.dtype))
    for add_arg, extract_arg in dispatch.create_args:
        add_arg(create_parser)

def build_update_parser(dispatch, action_parser):
    update_parser = action_parser.add_parser('update', help="Update "
                        "a(n) {0} record".format(dispatch.dtype))
    for add_arg, extract_arg in dispatch.update_args:
        add_arg(update_parser)

def build_delete_parser(dispatch, action_parser):
    delete_parser = action_parser.add_parser('delete', help="Delete "
                        "a(n) {0} record".format(dispatch.dtype))
    for add_arg, extract_arg in dispatch.delete_args:
        add_arg(delete_parser)

def build_detail_parser(dispatch, action_parser):
    detail_parser = action_parser.add_parser('detail', help="Detail "
                        "a(n) {0} record".format(dispatch.dtype))
    for add_arg, extract_arg in dispatch.detail_args:
        add_arg(detail_parser)

class DispatchA(ActionDispatch):
    resource_name = 'addressrecord'
    dtype = 'A'

    create_args = [
        fqdn_argument('fqdn'), # ~> (labmda, lambda)
        ttl_argument('ttl'),
        ip_argument('ip_str'),
        view_arguments('views'),
        comment_argument('comment')]

    update_args = create_args + [
        update_pk_argument('pk', dtype)
    ]

    delete_args = [
        delete_pk_argument('pk', dtype)
    ]

    detail_args = [detail_pk_argument('pk', dtype)]

    def get_create_data():
        data = super(ActionDispatchA, self).get_create_data()
        data['ip_type'] = 4
        return data

    def get_update_data():
        data = super(ActionDispatchA, self).get_update_data()
        data['ip_type'] = 4
        return data

dispatches.append(DispatchA())

class DispatchAAAA(DispatchA):
    dtype = 'AAAA'
    def get_create_data():
        data = super(ActionDispatchA, self).get_create_data()
        data['ip_type'] = 6
        return data

    def get_update_data():
        data = super(ActionDispatchA, self).get_update_data()
        data['ip_type'] = 6
        return data

dispatches.append(DispatchAAAA())

def dispatch(nas):
    for dispatch in dispatches:
        if dispatch.dtype == nas.dtype:
            try:
                getattr(dispatch, nas.action)(nas)
            except AttributeError:
                print "ERROR: Something went terrible wrong"
                print nas
