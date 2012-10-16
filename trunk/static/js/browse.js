/* search.js */

$(function() {
    $('#id_list_name').autocomplete({
        source: 'archive/ajax/list/',
        minLength: 1,
        select: function( event, ui ) {
            // window.location="/archive/browse/" + ui.item.label;
            window.location="/archive/search/?email_list=" + ui.item.label;
            return false;
        }
    });
    $('input[type=text]').focus();
});
