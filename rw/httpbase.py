# Copyright 2014 Florian Ludwig
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
from __future__ import absolute_import, division, print_function, with_statement

import tornado.web
import tornado.httpserver
from tornado import gen
from tornado.web import HTTPError

import rw.scope
import rw.routing


class Application(object):
    def __init__(self, handler=None, root=None):
        """rueckenwind Application to plug into tornado's httpserver.

        Either `root` or `handler` must be specified.

        :param rw.http.Module root: The root module to serve
        :param handler: The request handler (should subclass `tornado.web.RequestHandler`)
        """
        self.settings = {}
        self.root = root
        if self.root:
            self.root.setup()
            self.handler = handler if handler is not None else RequestHandler
        else:
            self.handler = handler
            assert handler is not None

        self.scope = rw.scope.Scope()
        self._wsgi = False  # wsgi is not supported

    def __call__(self, request):
        """Called by `tornado.httpserver.HTTPServer` to handle a request."""
        with self.scope():
            request_scope = rw.scope.Scope()
            with request_scope():
                handler = self.handler(self, request)
                handler._execute([])

    @gen.coroutine
    def setup(self):
        with self.scope():
            # default plugins
            self.scope.activate(rw.routing.plugin)
            # user plugins
            # TODO

    def log_request(self, request):
        print(request)


class RequestHandler(tornado.web.RequestHandler):
    def __init__(self, application, request, **kwargs):
        # The super class is not called since it creates
        # some structures we do not care about.  Since
        # the "not caring" leads to memory leaks they
        # are not created in the first place.

        self.application = application
        self.request = request
        self._headers_written = False
        self._finished = False
        self._auto_finish = False  # vanilla tornado defaults to True
        self._transforms = None  # will be set in _execute
        self.clear()
        self.initialize(**kwargs)

    def render(self, template_name, **kwargs):
        """Render..."""
        raise NotImplementedError()

    def render_string(self, template_name, **kwargs):
        """Generate the given template with the given arguments.

        We return the generated byte string (in utf8). To generate and
        write a template as a response, use render() above.
        """
        raise NotImplementedError()

    def get_template_namespace(self):
        """Returns a dictionary to be used as the default template namespace.

        May be overridden by subclasses to add or modify values.

        The results of this method will be combined with additional
        defaults in the `tornado.template` module and keyword arguments
        to `render` or `render_string`.
        """
        raise NotImplementedError()

    def create_template_loader(self, template_path):
        """Returns a new template loader for the given path.

        May be overridden by subclasses.  By default returns a
        directory-based loader on the given path, using the
        ``autoescape`` application setting.  If a ``template_loader``
        application setting is supplied, uses that instead.
        """
        raise NotImplementedError()

    def flush(self, include_footers=False, callback=None):
        """Flushes the current output buffer to the network.

        The ``callback`` argument, if given, can be used for flow control:
        it will be run when all flushed data has been written to the socket.
        Note that only one flush callback can be outstanding at a time;
        if another flush occurs before the previous flush's callback
        has been run, the previous callback will be discarded.
        """
        chunk = b"".join(self._write_buffer)
        self._write_buffer = []
        if not self._headers_written:
            self._headers_written = True
            for transform in self._transforms:
                self._status_code, self._headers, chunk = \
                    transform.transform_first_chunk(
                        self._status_code, self._headers, chunk, include_footers)
            headers = self._generate_headers()
        else:
            for transform in self._transforms:
                chunk = transform.transform_chunk(chunk, include_footers)
            headers = b""

        # Ignore the chunk and only write the headers for HEAD requests
        if self.request.method == "HEAD":
            if headers:
                self.request.write(headers, callback=callback)
            return

        self.request.write(headers + chunk, callback=callback)

    def finish(self, chunk=None):
        """Finishes this response, ending the HTTP request."""
        if self._finished:
            raise RuntimeError("finish() called twice.  May be caused "
                               "by using async operations without the "
                               "@asynchronous decorator.")

        if chunk is not None:
            self.write(chunk)

        # Automatically support ETags and add the Content-Length header if
        # we have not flushed any content yet.
        if not self._headers_written:
            if (self._status_code == 200 and
                        self.request.method in ("GET", "HEAD") and
                        "Etag" not in self._headers):
                self.set_etag_header()
                if self.check_etag_header():
                    self._write_buffer = []
                    self.set_status(304)
            if self._status_code == 304:
                assert not self._write_buffer, "Cannot send body with 304"
                self._clear_headers_for_304()
            elif "Content-Length" not in self._headers:
                content_length = sum(len(part) for part in self._write_buffer)
                self.set_header("Content-Length", content_length)

        if hasattr(self.request, "connection"):
            # Now that the request is finished, clear the callback we
            # set on the HTTPConnection (which would otherwise prevent the
            # garbage collection of the RequestHandler when there
            # are keepalive connections)
            self.request.connection.set_close_callback(None)

        self.flush(include_footers=True)
        self.request.finish()
        self._log()
        self._finished = True
        self.on_finish()

    # methods to investigate for overwriting
    # def locale(self):
    # def get_user_locale(self):
    # def get_browser_locale(self, default="en_US"):
    # def current_user(self):
    # def current_user(self, value):
    # def get_current_user(self):
    # def _when_complete(self, result, callback):

    def _execute(self, transforms, *args, **kwargs):
        """Executes this request with the given output transforms."""
        self._transforms = transforms
        try:
            if self.request.method not in self.SUPPORTED_METHODS:
                raise HTTPError(405)

            # If XSRF cookies are turned on, reject form submissions without
            # the proper cookie
            if self.request.method not in ("GET", "HEAD", "OPTIONS") and \
                    self.application.settings.get("xsrf_cookies"):
                self.check_xsrf_cookie()
            self._when_complete(self.prepare(), self._execute_method)
        except Exception as e:
            self._handle_request_exception(e)

    def _execute_method(self):
        self.application.root._handle_request(self)

    # overwrite methodes that are not supported to make sure
    # they get not used by accident.
    # TODO: point to alternatives in doc strings

    def get_template_path(self):
        """tornado API, not available in rw"""
        raise NotImplementedError()

    def static_url(self, path, include_host=None, **kwargs):
        """tornado API, not available in rw"""
        raise NotImplementedError()

    def reverse_url(self, name, *args):
        """tornado API, not available in rw"""
        raise NotImplementedError()

    def get_login_url(self):
        """tornado API, not available in rw"""
        raise NotImplementedError()

    def _ui_module(self, name, module):
        """tornado internal method, not used in rw"""
        raise NotImplementedError()

    def _ui_method(self, method):
        """tornado internal method, not used in rw"""
        raise NotImplementedError()