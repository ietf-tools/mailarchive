/* search.js */

$(function() {
    $('#id_list_name').autocomplete({
        source: 'archive/ajax/list/',
        minLength: 1,
        select: function( event, ui ) {
            window.location="/archive/browse/" + ui.item.label;
            return false;
        }
    });
});
