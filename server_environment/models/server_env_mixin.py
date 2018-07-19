# Copyright 2018 Camptocamp (https://www.camptocamp.com).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models
from ..serv_config import serv_config

_logger = logging.getLogger(__name__)


class ServerEnvMixin(models.AbstractModel):
    """Mixin to add server environment in existing models

    Usage::

        class StorageBackend(models.Model):
            _name = "storage.backend"
            _inherit = ["storage.backend", "server.env.mixin"]

            @property
            def _server_env_fields(self):
                return {"directory_path": 'get'}

    With the snippet above, the "storage.backend" model now uses a server
    environment configuration for the field ``directory_path``.

    Under the hood, this mixin automatically replaces the original field
    by a computed field that reads from the configuration files.

    By default, it looks for the configuration in a section named
    ``[model_name.Record Name]`` where ``model_name`` is the ``_name`` of the
    model with ``.`` replaced by ``_``. It can be customized by overriding the
    method :meth:`~server_env_section_name`.

    For each field transformed to an env-computed field, a companion field
    ``<field>_env_default`` is automatically created. When it's value is set
    and the configuration files do not contain a key, the env-computed field
    uses the default value stored in database. If a key is empty, the
    env-computed field has an empty value.
    """
    _name = 'server.env.mixin'

    server_env_defaults = fields.Serialized()

    @property
    def _server_env_fields(self):
        """Dict of fields to replace by fields computed from env

        To override in models. The dictionary is:
        {'name_of_the_field': 'name_of_the_configparser_getter'}

        The configparser getter can be one of: get, getbool, getint

        Example::

            @property
            def _server_env_fields(self):
                base_fields = super()._server_env_fields
                sftp_fields = {
                    "sftp_server": "get",
                    "sftp_port": "getint",
                    "sftp_login": "get",
                    "sftp_password": "get",
                }
                sftp_fields.update(base_fields)
                return sftp_fields
        """
        return {}

    @api.multi
    def _server_env_section_name(self):
        """Name of the section in the configuration files

        Can be customized in your model
        """
        self.ensure_one()
        return ".".join(
            (self._name.replace(".", "_"), self.name)
        )

    @api.multi
    def _server_env_read_from_config(self, section_name, field_name,
                                     config_getter):
        self.ensure_one()
        try:
            getter = getattr(serv_config, config_getter)
            value = getter(section_name, field_name)
        except:
            _logger.exception(
                "error trying to read field %s in section %s",
                field_name,
                section_name,
            )
            return False
        return value

    @api.multi
    def _compute_server_env(self):
        for record in self:
            for field_name, getter_name in self._server_env_fields.items():
                section_name = self._server_env_section_name()
                if (section_name in serv_config
                        and field_name in serv_config[section_name]):

                    value = self._server_env_read_from_config(
                        section_name, field_name, getter_name
                    )

                else:
                    default_field = self._server_env_default_fieldname(
                        field_name
                    )
                    value = record[default_field]

                record[field_name] = value

    def _server_env_default_fieldname(self, base_field_name):
        return '%s_env_default' % (base_field_name,)

    def _server_env_transform_field_to_read_from_env(self, field):
        """Transform the original field in a computed field"""
        field.compute = '_compute_server_env'
        field.store = False
        field.copy = False
        field.sparse = None

    def _server_env_add_default_field(self, base_field):
        fieldname = self._server_env_default_fieldname(base_field.name)
        if fieldname not in self._fields:
            base_field_cls = base_field.__class__
            field_args = base_field.args
            field_args.pop('_sequence', None)
            field_args.update({
                'sparse': 'server_env_defaults',
                'automatic': True,
            })
            field = base_field_cls(**field_args)
            self._add_field(fieldname, field)

    @api.model
    def _setup_base(self):
        super()._setup_base()
        for fieldname in self._server_env_fields:
            field = self._fields[fieldname]
            self._server_env_transform_field_to_read_from_env(field)
            self._server_env_add_default_field(field)
