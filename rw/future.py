

from jinja2 import nodes
from jinja2.ext import Extension


class CachedPartExtension(Extension):
    """Test jinja2 extentions"""
    # a set of names that trigger the extension.
    tags = set(['part'])

    def __init__(self, environment):
        super(CachedPartExtension, self).__init__(environment)

        # add the defaults to the environment
        environment.extend(
            fragment_cache_prefix='',
            fragment_cache=None
        )

    def parse(self, parser):
        # the first token is the token that started the tag.  In our case
        # we only listen to ``'cache'`` so this will be a name token with
        # `cache` as value.  We get the line number so that we can give
        # that line number to the nodes we create by hand.
        lineno = parser.stream.next().lineno
        print
        print 'stream', list(parser.stream)
        # now we parse a single expression that is used as cache key.
        args = [parser.parse_expression()]

        # if there is a comma, the user provided a timeout.  If not use
        # None as second parameter.
        if parser.stream.skip_if('comma'):
            args.append(parser.parse_expression())
        else:
            args.append(nodes.Const(None))

        # now we parse the body of the cache block up to `endpart` and
        # drop the needle (which would always be `endpart` in that case)
        body = parser.parse_statements(['name:endpart'], drop_needle=True)

        # now return a `CallBlock` node that calls our _cache_support
        # helper method on this extension.
        return nodes.CallBlock(self.call_method('_cache_support', args),
                               [], [], body).set_lineno(lineno)

    def _cache_support(self, name, timeout, caller):
        """Helper callback."""
        #key = self.environment.fragment_cache_prefix + name

        # try to load the block from the cache
        # if there is no fragment in the cache, render it and store
        # it in the cache.
        print 'get cache', name
        #rv = self.environment.fragment_cache.get(key)
        # return rv
        #if rv is not None:
        #    return rv
        rv = caller()
        #self.environment.fragment_cache.add(key, rv, timeout)
        return rv


