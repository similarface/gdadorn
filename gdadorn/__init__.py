# -*- coding: utf-8 -*-
# @Time    : 2019/8/5 上午10:11
# @Author  : similarface
# @Site    :
# @File    : __init__.py.py
# @Software: PyCharm

import os
import json
import psutil
from traitlets import Float, Int, default
from traitlets.config import Configurable
from notebook.utils import url_path_join
from notebook.base.handlers import IPythonHandler
from tornado import web
from notebook.base.handlers import AuthenticatedFileHandler
from notebook.utils import is_hidden, url_path_join, url_is_absolute, url_escape
from tornado.routing import Rule

from notebook.services.contents.handlers import validate_model, ContentsHandler,ModifyCheckpointsHandler
from notebook.utils import maybe_future
from tornado import gen, web
from jupyter_client.jsonutil import date_default


class MetricsHandler(IPythonHandler):
    @web.authenticated
    def get(self):
        config = self.settings['gdadorn_display_config']
        cur_process = psutil.Process()
        all_processes = [cur_process] + cur_process.children(recursive=True)
        # 使用的内存
        rss = sum([p.memory_info().rss for p in all_processes])
        limits = {}
        if config.mem_limit != 0:
            limits['memory'] = {
                'rss': config.mem_limit
            }
            if config.mem_warning_threshold != 0:
                limits['memory']['warn'] = (config.mem_limit - rss) < (config.mem_limit * config.mem_warning_threshold)
        metrics = {
            'rss': rss,
            'limits': limits,
        }
        self.write(json.dumps(metrics))

import time
def md5str(string):
    import hashlib
    m = hashlib.sha256()
    m.update(string.encode("utf-8"))
    return m.hexdigest()


class ContentsMonitorHandler(ContentsHandler):

    md5cache = {}

    def _finish_model(self, model, location=True):
        """Finish a JSON request with a model, setting relevant headers, etc."""
        if location:
            location = self.location_url(model['path'])
            self.set_header('Location', location)
        self.set_header('Last-Modified', model['last_modified'])
        self.set_header('Content-Type', 'application/json')
        self.finish(json.dumps(model, default=date_default))

    @web.authenticated
    @gen.coroutine
    def put(self, path=''):
        """Saves the file in the location specified by name and path.

        PUT is very similar to POST, but the requester specifies the name,
        whereas with POST, the server picks the name.

        PUT /api/contents/path/Name.ipynb
          Save notebook at ``path/Name.ipynb``. Notebook structure is specified
          in `content` key of JSON request body. If content is not specified,
          create a new empty notebook.
        """
        model = self.get_json_body()
        content = model.get("content",None)
        cells = None
        if content:
            cells = content.get('cells',None)
        if cells:
            source = []
            username = self.current_user.get("name", "")
            header = "\n### " + time.strftime("%Y%-m-%d %H:%M:%S", time.localtime()) + "\t" + username + "\t" + path + "\n"
            daystr=time.strftime("%Y%m%d", time.localtime())
            for cell in cells:
                source.append(cell.get('source',''))
            source.append("$$$ -END- \n\n")
            content_text = '\n'.join(source)
            content_md5 = md5str(content_text)
            old_content_md5 = self.md5cache.get(path,"")
            self.md5cache[path]=content_md5
            if old_content_md5!=content_md5:
                par_dir = f"/tmp/{username}/"
                if not os.path.exists(par_dir):
                    os.makedirs(par_dir)
                with open(f"{par_dir}{daystr}",'a') as oper:
                    oper.write(header+content_text)
        if model:
            if model.get('copy_from'):
                raise web.HTTPError(400, "Cannot copy with PUT, only POST")
            exists = yield maybe_future(self.contents_manager.file_exists(path))
            if exists:
                yield maybe_future(self._save(model, path))
            else:
                yield maybe_future(self._upload(model, path))
        else:
            yield maybe_future(self._new_untitled(path))



class DownLoadLimitHandler(AuthenticatedFileHandler):
    def validate_absolute_path(self, root, absolute_path):
        """Validate and return the absolute path.

        Requires tornado 3.1

        Adding to tornado's own handling, forbids the serving of hidden files.
        """

        abs_path = super(AuthenticatedFileHandler, self).validate_absolute_path(root, absolute_path)
        abs_root = os.path.abspath(root)
        fsize = os.path.getsize(abs_path)
        if fsize > 10240000 and not abs_path.endswith("nbpy_"):
            self.log.info(f"下载文件超过10M！ {abs_path}")
            raise web.HTTPError(400, reason="文件大小超过限制")

        if is_hidden(abs_path, abs_root) and not self.contents_manager.allow_hidden:
            self.log.info(
                "Refusing to serve hidden file, via 404 Error, use flag 'ContentsManager.allow_hidden' to enable")
            raise web.HTTPError(404)
        return abs_path



def _jupyter_server_extension_paths():
    return [{
        'module': 'gdadorn',
    }]


def _jupyter_nbextension_paths():
    return [{
        "section": "notebook",
        "dest": "gdadorn",
        "src": "static",
        "require": "gdadorn/main"
    }]


class ResourceUseDisplay(Configurable):
    """
    Holds server-side configuration for gdadorn
    """

    mem_warning_threshold = Float(
        0.1,
        help="""
        Warn user with flashing lights when memory usage is within this fraction
        memory limit.

        For example, if memory limit is 128MB, `mem_warning_threshold` is 0.1,
        we will start warning the user when they use (128 - (128 * 0.1)) MB.

        Set to 0 to disable warning.
        """,
        config=True
    )

    mem_limit = Int(
        0,
        config=True,
        help="""
        Memory limit to display to the user, in bytes.

        Note that this does not actually limit the user's memory usage!

        Defaults to reading from the `MEM_LIMIT` environment variable. If
        set to 0, no memory limit is displayed.
        """
    )

    @default('mem_limit')
    def _mem_limit_default(self):
        return int(os.environ.get('MEM_LIMIT', 0))


class HelloWorldHandler(IPythonHandler):
    def get(self):
        self.finish('Hello, world!')


def load_jupyter_server_extension(mfapp):
    """
    Called during notebook start
    """
    resuseconfig = ResourceUseDisplay(parent=mfapp)
    mfapp.web_app.settings['gdadorn_display_config'] = resuseconfig
    route_pattern = url_path_join(mfapp.web_app.settings['base_url'], '/metrics')
    mfapp.web_app.add_handlers('.*', [(route_pattern, MetricsHandler)])
    rules = mfapp.web_app.wildcard_router.rules
    index=0
    for rule in rules:
        if rule.target == AuthenticatedFileHandler:
            mfapp.web_app.wildcard_router.rules = [Rule(rule.matcher, DownLoadLimitHandler, rule.target_kwargs,
                                                        rule.name)] + mfapp.web_app.wildcard_router.rules

        if rule.target == ContentsHandler:
            mfapp.web_app.wildcard_router.rules[index] = Rule(rule.matcher, ContentsMonitorHandler, rule.target_kwargs,rule.name)
        index = index + 1