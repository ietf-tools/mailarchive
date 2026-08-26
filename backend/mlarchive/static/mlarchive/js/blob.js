/* blob.js */

var mailarchBlob = {

    init: function() {
        mailarchBlob.setupToggles();
    },

    setupToggles: function() {
        // setup message header toggle
        $('#msg-date').after('<a id="toggle-msg-header" class="toggle" href="#">Show header</a>');
        $('#toggle-msg-header').click(function(ev) {
            ev.preventDefault();
            $('#msg-header').toggle();
            $(this).html(($('#toggle-msg-header').text() == 'Show header') ? 'Hide header' : 'Show header');
        });
    }
}

$(function() {
    mailarchBlob.init();
});
