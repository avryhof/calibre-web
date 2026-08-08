# -*- coding: utf-8 -*-

"""Calibre-Web Sync plugin for Calibre desktop.

Pushes new/changed books (files, metadata, cover) from the Calibre library to
a Calibre-Web server and pulls new/changed books and metadata back, using the
server's sync API (/api/sync) authenticated with an X-API-Key header.
"""

from calibre.customize import InterfaceActionBase


class CalibreWebSyncPlugin(InterfaceActionBase):
    name = 'Calibre-Web Sync'
    description = 'Two-way sync of the library with a Calibre-Web server ' \
                  '(books, metadata and covers).'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'FamilyHub'
    version = (1, 0, 0)
    minimum_calibre_version = (5, 0, 0)
    actual_plugin = 'calibre_plugins.calibrewebsync.worker:CalibreWebSyncAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.calibrewebsync.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
