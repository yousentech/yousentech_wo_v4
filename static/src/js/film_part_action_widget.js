odoo.define('yousentech_wo_v4.film_part_action_widget', function (require) {
    "use strict";

    var AbstractField = require('web.AbstractField');
    var fieldRegistry = require('web.field_registry');

    var FilmPartActionWidget = AbstractField.extend({
        supportedFieldTypes: ['char'],

        events: {
            'click .o_open_action': '_onOpenAction',
        },

        _render: function () {
            this.$el.html(
                '<button type="button" class="btn btn-link o_open_action">' +
                '<i class="fa fa-external-link"></i>' +
                '</button>'
            );
        },

        _onOpenAction: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();

            var lineId = this.res_id;

            if (!lineId) {
                this.displayNotification({
                    title: "تنبيه",
                    message: "احفظ سطر الجزء أولاً ثم افتح التسعيرات أو العمولات.",
                    type: "warning",
                });
                return;
            }

            this.do_action({
                type: 'ir.actions.act_window',
                name: this.attrs.options.title || 'فتح',
                res_model: this.attrs.options.model,
                view_mode: 'tree,form',
                domain: [['part_line_id', '=', lineId]],
                context: {
                    default_part_line_id: lineId,
                },
                target: 'current',
            });
        },
    });

    fieldRegistry.add('film_part_action_widget', FilmPartActionWidget);
});