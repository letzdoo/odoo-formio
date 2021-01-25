# Copyright Nova Code (http://www.novacode.nl)
# See LICENSE file for full licensing details.

from odoo import fields, models, api, _

COMPONENT_TYPES = [
            ('checkbox', 'Checkbox'),
            ('datagrid', 'Data Grid'),
            ('email', 'Email'),
            ('number', 'Number'),
            ('phoneNumber', 'Phone Number'),
            ('select', 'Select'),
            ('selectboxes', 'Select Boxes'),
            ('signature', 'Signature'),
            ('textarea', 'Text Area'),
            ('textfield', 'Text Field'),
        ]


class FormioComponent(models.Model):
    _name = 'formio.component'
    _rec_name = 'display_name'
    _description = 'Formio Component'

    # ----------------------------------------------------------
    # Database
    # ----------------------------------------------------------

    label = fields.Char(
        string="Label"
    )

    display_name = fields.Char(
        string="Display Name",
        compute='_compute_display_name',
        readonly=True,
        store=True
    )

    key = fields.Char(
        string="Unique Identifier"
    )

    type = fields.Selection(
        selection=COMPONENT_TYPES,
        string="Type"
    )

    parent_id = fields.Many2one(
        'formio.component',
        string='Parent Component ID',
        index=True
    )

    parent_name = fields.Char(
        related='parent_id.display_name',
        string='Parent Component',
        readonly=True
    )

    child_ids = fields.One2many(
        'formio.component',
        'parent_id',
        string='Child Component'
    )

    builder_id = fields.Many2one(
        'formio.builder',
        string='Form Builder',
        required=True,
        ondelete='restrict'
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _compare_components(self, old_components, new_components):
        """
        Compares arrays with component keys.

        :param array old_components: an array with the old component keys to compare,
        :param array new_components: an array with the components which are actually in the builder scheme to compare,
        :return dict: with the deleted and added keys.

        {   'added': ['textArea10', 'dataGrid', ...],
            'deleted': ['textField1', 'textArea3', ...]
        }

        """
        new_components = set(new_components)
        old_components = set(old_components)

        added = new_components.difference(old_components)
        deleted = old_components.difference(new_components)

        result = {
            'added': list(added),
            'deleted': list(deleted)
        }
        return result

    def _get_components(self, builder_id, component_keys):
        """
        Returns multiple formio.component obj from component keys.

        :param int builder_id: the builder id to which the components are belongs,
        :param array component_keys keys of components,
        :return tulp: with the component_ids.
        """
        return self.search([
            ("builder_id", '=', builder_id),
            ("key", '=', component_keys)
        ])

    def _get_builder(self, builder_id):
        """
        Returns an builder_obj from builder_id.

        :param int builder_id the builder id which should be mapped to an builder_obj,
        :return tulp: with the builder_obj.
        """
        return self.env["formio.builder"].search([("id", '=', builder_id)])

    def _get_builder_component_keys(self, builder_id):
        """
        Fetch the components from specified builder and return it's component keys.

        :param int builder_id: the builder id where the components are located,
        :return array: with the component keys.
        """
        result = []
        builder_obj = self._get_builder(builder_id)
        for key, component in builder_obj._formio.components.items():
            if component.raw.get('input') and component.type != 'button':
                if any(component.type in i for i in COMPONENT_TYPES):
                    result.append(key)
        return result

    def _get_model_components_keys(self, builder_id):
        """
        Fetch the components from the formio.component model filter by specified builder_ids.

        :param int builder_id: the builder id which should be used to search the model,
        :return array: with the component keys.
        """
        result = []
        records = self.search([("builder_id", '=', builder_id)])
        for record in records:
            result.append(record.key)
        return result

    def _has_datagrid(self, builder_id):
        """
        Check builder schema for datagrid.

        :param int builder_id: the builder id where the components are located,
        :return boolean: True if builder_obj has a datagrid component else false.
        """
        builder_obj = self._get_builder(builder_id)
        for key, component in builder_obj._formio.components.items():
            if component.raw.get('input') and component.type == 'datagrid':
                return True
        return False

    def _in_datagrid(self, builder_id, component_key):
        """
        Checks if a component is in any datagrid.

        :param int builder_id: According builder_id to the component.
        :param int component_key: Component key to check.
        :return boolean: False if component isn't in any datagrid.
        :return string: Key of the parent datagrid.
        """
        builder_obj = self._get_builder(builder_id)
        datagrid = []

        for key, component in builder_obj._formio.components.items():
            if component.raw.get('input') and component.type == 'datagrid':
                datagrid.append(component)
        for grid in datagrid:
            if component_key in grid.labels.keys():
                return grid.key
        return False

    def _compute_parent_id(self, builder_id):
        """
        Computes the parent and child dependency of an formio.component object.
        """
        if not self._has_datagrid(builder_id):
            return

        keys = self._get_model_components_keys(builder_id)
        objects = self._get_components(builder_id, keys)

        for datagrid in objects:
            if datagrid.type != 'datagrid':
                return
            builder_id = datagrid.builder_id.id
            builder_obj = datagrid.builder_id
            datagrid_children = list(builder_obj._formio.components[datagrid.key].labels.keys())
            model_components = self._get_components(builder_id, datagrid_children)

            for component in model_components:
                if component not in datagrid.child_ids:
                    datagrid.child_ids += component

    @api.one
    @api.depends('label', 'parent_id')
    def _compute_display_name(self):
        """
        Computes the display name of formio.component.
        If it has parent it adds parents name to the display name.
        """
        if self.parent_id:
            self.display_name = '%s.%s (%s)' % (self.parent_id.key, self.key, self.label)
        else:
            self.display_name = '%s (%s)' % (self.key, self.label)

    def _write_components(self, builder_id, component_keys):
        """
        Writes the components with all required data to formio.component model.

        :param int builder_id: the builder id where the components are located,
        :param array component_keys: components which should be added to this model.
        """
        builder_obj = self._get_builder(builder_id)
        for component in component_keys:
            obj = builder_obj._formio.form_components[component]
            self.create({
                'label': obj.label,
                'key': obj.key,
                'type': obj.type,
                'builder_id': builder_id,
            })

        if self._has_datagrid(builder_id):
            self._compute_parent_id(builder_id)

    def _update_components(self, builder_id):
        """
        Checks for label changes and component position changes in datagrid.

        :param int builder_id: the builder id where the components are located,
        """
        builder_obj = self._get_builder(builder_id)

        for key, comp in builder_obj._formio.components.items():
            if not comp.raw.get('input') or comp.type == 'button':
                return

            component = self._get_components(builder_id, key)

            """
            Updating datagrid
            """
            grid = self._in_datagrid(builder_id, key)
            grid_record = self._get_components(builder_id, grid)
            if component.parent_id and grid != component.parent_id.key:
                component.parent_id = grid_record
            elif not component.parent_id and grid:
                component.parent_id = grid_record
            elif not grid:
                component.parent_id = ()

            """
            Updating component attributes
            """
            for obj in component:
                if obj.label != comp.label:
                    obj.label = comp.label

    def _delete_components(self, builder_id, component_keys):
        """
        Removes components from formio.component model.

        :param int builder_id: the builder id where the components are located,
        :param array component_keys: components which should be removed from this model.
        """
        components = self._get_components(builder_id, component_keys)
        components.unlink()

    # ----------------------------------------------------------
    # Public
    # ----------------------------------------------------------

    def synchronize_components(self, builder_ids):
        """
        Synchronize builder components with the formio.component model.

        :param array builder_ids: builder ids of components which should be synchronized
        and added or deleted to the formio.component model.
        """
        for builder_id in builder_ids:
            new_components = self._get_builder_component_keys(builder_id)
            old_components = self._get_model_components_keys(builder_id)
            components_dict = self._compare_components(old_components, new_components)

            if components_dict['added']:
                self._write_components(builder_id, components_dict['added'])
            if components_dict['deleted']:
                self._delete_components(builder_id, components_dict['deleted'])
            self._update_components(builder_id)
