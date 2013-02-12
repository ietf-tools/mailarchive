/* detail.js */

$(function() {
    $('#msg-header').hide()
    $('#msg-date').after('<a id="toggle" href="#">Show header</a>');
    $('#toggle').click(function(ev) { 
        $('#msg-header').toggle(); 
        $(this).html(($('#toggle').text() == 'Show header') ? 'Hide header' : 'Show header');
    });
});