# -*- coding: utf-8 -*-

"""Configuration for the Calibre-Web Sync plugin."""

from calibre.utils.config import JSONConfig

try:
    from PyQt5.QtWidgets import (QWidget, QDialog, QVBoxLayout, QFormLayout,
                                 QLineEdit, QCheckBox, QDialogButtonBox, QLabel)
except ImportError:  # pragma: no cover - fall back for newer Qt bindings
    from PyQt6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QFormLayout,
                                 QLineEdit, QCheckBox, QDialogButtonBox, QLabel)


prefs = JSONConfig('plugins/calibrewebsync')
prefs.defaults['server_url'] = 'http://localhost:8083'
prefs.defaults['api_key'] = ''
prefs.defaults['verify_ssl'] = True
prefs.defaults['push_changes'] = True
prefs.defaults['pull_changes'] = True
prefs.defaults['delete_removed'] = False
prefs.defaults['content_server_url'] = ''
prefs.defaults['report_content_server'] = True


class ConfigWidget(QWidget):
    """Simple settings panel shown from Preferences -> Plugins."""

    def __init__(self):
        QWidget.__init__(self)
        layout = QFormLayout(self)

        self.server_url_edit = QLineEdit(self)
        self.server_url_edit.setText(prefs['server_url'])
        self.server_url_edit.setPlaceholderText('http://localhost:8083')
        layout.addRow('Calibre-Web server URL', self.server_url_edit)

        self.api_key_edit = QLineEdit(self)
        self.api_key_edit.setText(prefs['api_key'])
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        layout.addRow('API key', self.api_key_edit)

        hint = QLabel('Create a key under Settings -> API Keys in Calibre-Web. '
                      'The key inherits the permissions of the user you assign it to.',
                      self)
        hint.setWordWrap(True)
        layout.addRow(hint)

        self.verify_ssl = QCheckBox('Verify TLS certificates', self)
        self.verify_ssl.setChecked(prefs['verify_ssl'])
        layout.addRow(self.verify_ssl)

        self.push_changes = QCheckBox('Push local changes to Calibre-Web', self)
        self.push_changes.setChecked(prefs['push_changes'])
        layout.addRow(self.push_changes)

        self.pull_changes = QCheckBox('Pull remote changes from Calibre-Web', self)
        self.pull_changes.setChecked(prefs['pull_changes'])
        layout.addRow(self.pull_changes)

        self.delete_removed = QCheckBox('Delete books that were removed on the '
                                        'other side (use with care)', self)
        self.delete_removed.setChecked(prefs['delete_removed'])
        layout.addRow(self.delete_removed)

        self.content_server_edit = QLineEdit(self)
        self.content_server_edit.setText(prefs['content_server_url'] or '')
        self.content_server_edit.setPlaceholderText('http://localhost:8080')
        layout.addRow('Calibre desktop content server URL (optional)',
                      self.content_server_edit)

        self.report_content_server = QCheckBox('Report content server status to '
                                               'Calibre-Web', self)
        self.report_content_server.setChecked(prefs['report_content_server'])
        layout.addRow(self.report_content_server)

    def save_settings(self):
        prefs['server_url'] = self.server_url_edit.text().strip().rstrip('/')
        prefs['api_key'] = self.api_key_edit.text().strip()
        prefs['verify_ssl'] = self.verify_ssl.isChecked()
        prefs['push_changes'] = self.push_changes.isChecked()
        prefs['pull_changes'] = self.pull_changes.isChecked()
        prefs['delete_removed'] = self.delete_removed.isChecked()
        prefs['content_server_url'] = self.content_server_edit.text().strip().rstrip('/')
        prefs['report_content_server'] = self.report_content_server.isChecked()


class ConfigDialog(QDialog):
    """Edit-only dialog shown from the toolbar action when no server is
    configured yet."""

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle('Calibre-Web Sync settings')
        layout = QVBoxLayout(self)
        widget = ConfigWidget()
        layout.addWidget(widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._widget = widget

    def save_settings(self):
        self._widget.save_settings()
