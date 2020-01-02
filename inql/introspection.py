from __future__ import print_function

import urllib2, urllib
import argparse
import time
import os
import json
import sys
from urlparse import urlparse
from datetime import date

from utils import string_join, mkdir_p
from generators import html, query, schema

# Hack-ish way to handle unicode (finger crossed)
reload(sys)
sys.setdefaultencoding('UTF8')


def wrap_exit(method, exceptions = (OSError, IOError)):
    """
    Wrap exit method to write the error and reset colors to the output before exiting.
    :param method: exit method
    :param exceptions:
    :return:
    """
    def fn(*args, **kwargs):
        try:
            print(reset)
            return method(*args, **kwargs)
        except exceptions:
            sys.exit('Can\'t open \'{0}\'. Error #{1[0]}: {1[1]}'.format(args[0], sys.exc_info()[1].args))

    return fn
exit = wrap_exit(exit)

# colors for terminal messages
red = ""
green = ""
white = ""
yellow = ""
reset = ""

def posix_colors():
    """
    Setup global POSIX shell colors.
    :return: None
    """
    global red, green, white, yellow, reset
    red = "\033[1;31;10m[!] "
    green = "\033[1;32;10m[+] "
    white = "\033[1;37;10m"
    yellow = "\033[1;33;10m[!] "
    reset = "\033[0;0m"

def supports_color():
    """
    Returns True if the running system's terminal supports color, and False
    otherwise.
    """
    plat = sys.platform
    supported_platform = plat != 'Pocket PC' and (plat != 'win32' or
                                                  'ANSICON' in os.environ)
    # isatty is not always implemented, #6223.
    is_a_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    return supported_platform and is_a_tty


if supports_color():
    posix_colors()


def query_result(target, key, proxyDict, headers={}):
    """
    Execute the introspection query against the GraphQL endpoint

    :param target:
        Expects a valid URL ex. https://example.com/graphql
        Raise an exception if HTTP/HTTPS schema is missing

    :param key:
        Optional parameter to be used as authentication header
        "Basic dXNlcjp0ZXN0"
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"

    :param proxyDict:
        Optional parameter to be used as web proxy to go through
        ex. http://127.0.0.1:8080

    :return:
        Returns a dictionary objects to be parsed
    """
    headers = headers.copy()
    # Introspection Query
    # -----------------------
    introspection_query =  "query IntrospectionQuery{__schema{queryType{name}mutationType{name}subscriptionType{name}types{...FullType}directives{name description locations args{...InputValue}}}}fragment FullType on __Type{kind name description fields(includeDeprecated:true){name description args{...InputValue}type{...TypeRef}isDeprecated deprecationReason}inputFields{...InputValue}interfaces{...TypeRef}enumValues(includeDeprecated:true){name description isDeprecated deprecationReason}possibleTypes{...TypeRef}}fragment InputValue on __InputValue{name description type{...TypeRef}defaultValue}fragment TypeRef on __Type{kind name ofType{kind name ofType{kind name ofType{kind name ofType{kind name ofType{kind name ofType{kind name ofType{kind name}}}}}}}}"
    old_introspection_query =  "query IntrospectionQuery{__schema{queryType{name}mutationType{name}subscriptionType{name}types{...FullType}directives{name description args{...InputValue}onOperation onFragment onField}}}fragment FullType on __Type{kind name description fields(includeDeprecated:true){name description args{...InputValue}type{...TypeRef}isDeprecated deprecationReason}inputFields{...InputValue}interfaces{...TypeRef}enumValues(includeDeprecated:true){name description isDeprecated deprecationReason}possibleTypes{...TypeRef}}fragment InputValue on __InputValue{name description type{...TypeRef}defaultValue}fragment TypeRef on __Type{kind name ofType{kind name ofType{kind name ofType{kind name}}}}"
    # -----------------------
    if 'User-Agent' not in headers:
        headers['User-Agent'] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:55.0) Gecko/20100101 Firefox/55.0"

    if key:
        headers['Authorization'] = key

    try:
        # Issue the Introspection request against the GraphQL endpoint
        data = urllib.urlencode({"query": introspection_query})
        if proxyDict:
            proxy = urllib2.ProxyHandler(proxyDict)
            opener = urllib2.build_opener(proxy)
            urllib2.install_opener(opener)
        request = urllib2.Request(target, data, headers=headers)
        contents = urllib2.urlopen(request).read()
        return contents

    except urllib2.HTTPError as e:
        print(string_join(red, str(e), reset))

    except urllib2.URLError as e:
        print(string_join(red, str(e), reset))


def main():
    """
    Query a GraphQL endpoint with introspection in order to retrieve the documentation of all the Queries, Mutations & Subscriptions.
    It will also generate Queries, Mutations & Subscriptions templates (with optional placeholders) for all the known types.

    :return:
        none
    """
    # Args parser definition
    # -----------------------
    parser = argparse.ArgumentParser(prog="inql", description="GraphQL Scanner")
    parser.add_argument("-t", default=None, dest="target",
                        help="Remote GraphQL Endpoint (https://<Target_IP>/graphql)")
    parser.add_argument("-f", dest="schema_json_file", default=None, help="Schema file in JSON format")
    parser.add_argument("-k", dest="key", help="API Authentication Key")
    parser.add_argument('-p', dest="proxy", default=None,
                        help='IP of web proxy to go through (http://127.0.0.1:8080)')
    parser.add_argument('--header', dest="headers", nargs=2, action='append')
    parser.add_argument("-d", dest="detect", action='store_true', default=False,
                        help="Replace known GraphQL arguments types with placeholder values (useful for Burp Suite)")
    parser.add_argument("--generate-html", dest="generate_html", action='store_true', default=True,
                        help="Generate HTML Documentation")
    parser.add_argument("--generate-schema", dest="generate_schema", action='store_true', default=True,
                        help="Generate JSON Schema Documentation")
    parser.add_argument("--generate-queries", dest="generate_queries", action='store_true', default=True,
                        help="Generate Queries")
    parser.add_argument("-o", dest="output_directory", default=os.getcwd(),
                        help="Output Directory")
    args = parser.parse_args()
    # -----------------------

    mkdir_p(args.output_directory)
    os.chdir(args.output_directory)

    return init(args, lambda: parser.print_help())


def init(args, print_help=None):
    """
    Main Introspection method.

    :param args: arg parser alike arguments
    :param print_help: print help lambda
    :return: None
    """
    # At least one between -t or -f (target) parameters must be set
    if args.target is None and args.schema_json_file is None:
        print(string_join(red, "Remote GraphQL Endpoint OR a Schema file in JSON format must be specified!", reset))
        if print_help:
            print_help()
            exit(1)

    # Only one of them -t OR -f :)
    if args.target is not None and args.schema_json_file is not None:
        print(string_join(red, "Only a Remote GraphQL Endpoint OR a Schema file in JSON format must be specified, not both!", reset))
        if print_help:
            print_help()
            exit(1)

    # Takes care of any configured proxy (-p param)
    if args.proxy is not None:
        print(string_join(yellow, "Proxy ENABLED: ", args.proxy, reset))
        proxyDict = {"http": args.proxy, "https": args.proxy}
    else:
        proxyDict = {}

    # Generate Headers object
    headers = {}
    for k, v in args.headers:
        headers[k] = v

    if args.target is not None or args.schema_json_file is not None:
        if args.target is not None:
            # Acquire GraphQL endpoint URL as a target
            URL = urlparse(args.target).netloc
        else:
            # Acquire a local JSON file as a target
            print(string_join(yellow, "Parsing local schema file", reset))
            URL = os.path.splitext(os.path.basename(args.schema_json_file))[0]
        if args.detect:
            print(string_join(yellow, "Detect arguments is ENABLED, known types will be replaced with placeholder values", reset))
        # Used to generate 'unique' file names for multiple documentation
        timestamp = str(int(time.time()))  # Can be printed with: str(int(timestamp))
        today = str(date.today())
        # -----------------------
        # Custom Objects are required for fields names in the documentation and templates generation
        # old -c parameter, enabled by default
        custom = True
        # Generate the documentation for the target
        if args.target is not None:
            # Parse response from the GraphQL endpoint
            argument = query_result(args.target, args.key, proxyDict, headers)
            # returns a dict
            argument = json.loads(argument)
        else:
            # Parse the local JSON file
            with open(args.schema_json_file, "r") as s:
                result_raw = s.read()
                argument = json.loads(result_raw)

        if args.generate_schema:
            schema.generate(argument,
                            fpath=os.path.join(URL, "schema-%s-%s.json" % (today, timestamp)))
        if args.generate_html:
            html.generate(argument,
                          fpath=os.path.join(URL, "doc-%s-%s.html" % (today, timestamp)),
                          custom=custom,
                          target=args.target)
        if args.generate_queries:
            query.generate(argument,
                           qpath=os.path.join(URL, "%s", today, timestamp, "%s"),
                           detect=args.detect,
                           custom=custom,
                           green_print=lambda s: print(string_join(green, "Writing Queries Templates", reset)))

    else:
        # Likely missing a required arguments
        print("Missing Arguments")
        if print_help:
            print(white)
            print_help()
            print(reset)
            exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Catch CTRL+C, it will abruptly kill the script
        print(string_join(red, "Exiting...", reset))
        exit(-1)