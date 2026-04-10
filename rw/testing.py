import tornado.testing

import rw.server


class AsyncHTTPTestCase(tornado.testing.AsyncHTTPTestCase):
    def get_http_server(self):
        # setup ._app before creating http server
        self.io_loop.run_sync(rw.server.start)
        return super(AsyncHTTPTestCase, self).get_http_server()
