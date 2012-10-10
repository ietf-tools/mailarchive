/* search.js */

$(function() {
    /*
    $("input").keydown(function(event) {
        if (event.keyCode == '13') {
            event.preventDefault();
            // go to next form field
        }
    });
    */
    
    function add_to_list(list, id, label) {
        list.append('<li><a href="' + id + '"><img src="/img/delete.png" alt="delete"></a> ' + label + '</li>');
    }

    function get_string(datastore) {
        var values = [];
        for (var i in datastore) { 
            values.push(datastore[i]);
        }
        return values.join();
    }
    
    function jump_to(label) {
        window.location="/archive/browse/" + label;
    }
    
    function init_search() {
        $("#search-container input#id_q").focus();
        $("#advanced-search input#id_q").focus();
        /*
        $('#advanced-search').hide();
        
        $('#asShow').click(function() {
          $('#advanced-search').show();
          $('#basic-search').hide();
        });
        $('#asHide').click(function() {
          $('#advanced-search').hide();
          $('#basic-search').show();
        });
        */
    }
    
    function setup_ajax_browse(field, list, searchfield, url) {
        searchfield.autocomplete({
            source: url,
            minLength: 1,
            select: function( event, ui ) {
                jump_to(ui.item.label);
                return false;
            }
        });
    }
    
    function setup_ajax(field, list, searchfield, url) {
        var datastore = {};
        if(field.val() != '')
            datastore = $.evalJSON(field.val())

        $.each(datastore, function(k, v) {
            add_to_list(list, k, v);
        });
        
        searchfield.autocomplete({
            source: url,
            minLength: 1,
            select: function( event, ui ) {
                datastore[ui.item.id] = ui.item.label;
                field.val(get_string(datastore));
                searchfield.val('');
                add_to_list(list, ui.item.id, ui.item.label);
                return false;
            }
        });

        list.delegate("a", "click", function() {
            delete datastore[$(this).attr("href")];
            field.val(get_string(datastore));
            $(this).closest("li").remove();
            return false;
        });
    }

    function setup_buttons() {
        $('#sort-date-button').click(function() {
            $('#id_so').val('date');
            $('form#id_search_form').submit();
        });
        $('#sort-from-button').click(function() {
            $('#id_so').val('frm');
            $('form#id_search_form').submit();
        });
    }
    
    /* auto select first item in result list */
    function select_first_msg() {
        var row = $('table#msg-table tr:first');
        $('table#msg-table tr').css('background-color','#FFFFFF');
        row.css('background-color','#DDECFE');
        var msgId = row.find("td:last").html();
        /* TODO: this call needs auth */
        $('#msg-body').load('/archive/ajax/msg/?term=' + msgId);
    }
    
    /* handle message select from list */
    $('table#msg-table tr').click(function () {
        /* $(this).toggleClass('hilite'); */
        $('table#msg-table tr').css('background-color','#FFFFFF');
        $(this).css('background-color','#DDECFE');
        var msgId = $(this).find("td:last").html();
        /* TODO: this call needs auth */
        $('#msg-body').load('/archive/ajax/msg/?term=' + msgId);
    });
    
    /* enable arrow key navigation of message list */
    $('table#msg-table').keypress(function (e) {
        alert(e);
    });

    /* setup list widget */
    if ( $("form.advanced").length > 0){
      setup_ajax($("#email_list"), $("#email_list_list"), $("#email_list_search"), "archive/ajax/list/");
    }
    
    setup_buttons();
    /* setup_ajax_browse($("#id_list_name"), $("#list_name_list"), $("#id_list_name_search"), "{% url ajax_get_list %}"); */
    init_search();
    select_first_msg();
});
