/* detail.js */

var mailarchDetails = {

    init: function() {
        mailarchDetails.progressiveFeatures();
        mailarchDetails.setupToggles();
        mailarchDetails.initNavLinks();
    },

    doStaticNavLinks: function() {
        $("#date-index").attr("href", $("#msg-detail").data('static-date-index-url'));
        $("#thread-index").attr("href", $("#msg-detail").data('static-thread-index-url'));
    },

    doRegularNavLinks: function() {
        $("#date-index").attr("href", $("#msg-detail").data('date-index-url'));
        $("#thread-index").attr("href", $("#msg-detail").data('thread-index-url'));
    },

    legacyOn: function() {
        mailarchDetails.doStaticNavLinks();
    },

    legacyOff: function() {
        mailarchDetails.doRegularNavLinks();
    },

    progressiveFeatures: function() {
    // Progressive Javascript setup
        // Show progressive elements
        $('.js-off').addClass('js-on').removeClass('js-off');
    },

    initNavLinks: function() {
        if(base.isLegacyOn){
            mailarchDetails.doStaticNavLinks();
        }
    },

    setupToggles: function() {
        // setup message header toggle
        $('#msg-date').after('<a id="toggle-msg-header" class="toggle" href="#">Show header</a>');
        $('#toggle-msg-header').click(function(ev) { 
            $('#msg-header').toggle(); 
            $(this).html(($('#toggle-msg-header').text() == 'Show header') ? 'Hide header' : 'Show header');
        });
        // setup navigation bar toggle
        $('#toggle-nav').click(function(ev) {
            $('.navbar-msg-detail').toggle();
            $(this).html(($('#toggle-nav').text() == 'Show Navigation Bar') ? 'Hide Navigation Bar' : 'Show Navigation Bar');
            if($('.navbar-msg-detail').is(':hidden')) {
                $.cookie("show_navbar", "false", { expires: 365, path: '/arch/msg' });
            } else {
                $.cookie("show_navbar", "true", { expires: 365, path: '/arch/msg' });   
            }
        });

        var show_navbar = $.cookie("show_navbar");
        if(show_navbar == "false") {
            $('.navbar-msg-detail').hide();
            $('#toggle-nav').text('Show Navigation Bar');
        }
    }
}

$(function() {
    mailarchDetails.init();
});