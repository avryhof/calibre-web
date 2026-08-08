/* This file is part of the Calibre-Web fork.
 * Toggle reveal of stored API key values (only populated in development/test
 * app modes) on the admin API keys page.
 */

(function ($) {
    'use strict';

    $('.api-key-toggle').on('click', function () {
        var $btn = $(this);
        var $code = $btn.closest('td').find('.api-key-reveal');
        var visible = $code.data('visible') === true;
        if (visible) {
            $code.data('visible', false).text('hidden');
            $btn.text('View');
        } else {
            $code.data('visible', true).text($code.data('key-value'));
            $btn.text('Hide');
        }
    });
})(jQuery);
