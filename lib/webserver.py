# This could be used to build a more dynamic/advanced image browser. For now just start a server
import http.server
import _thread as thread


def _create_handler(directory):
    def _init(self, *args, **kwargs):
        return http.server.SimpleHTTPRequestHandler.__init__(self, *args, directory=self.directory, **kwargs)
    return type(f'HandlerFrom<{directory}>',
                (http.server.SimpleHTTPRequestHandler,),
                {'__init__': _init, 'directory': directory})


class WebServer:
    def __init__(self, directory: str, port: int):
        self.port = port
        self.directory = directory

    def start(self):
        thread.start_new_thread(self._create_server, ())

    def _create_server(self):
        server = http.server.ThreadingHTTPServer(("", self.port), _create_handler(directory=self.directory))
        server.serve_forever()


