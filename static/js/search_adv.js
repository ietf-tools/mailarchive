/* search_adv.js */

/*
This script uses the JQuery Query String Object plugin
http://archive.plugins.jquery.com/project/query-object
*/

$(function() {
    function add_to_list(list, id, label) {
        list.append('<li><a class="listlink" href="' + id + '">' + label + '<img id="delete-icon" src="/static/admin/img/icon_deletelink.gif" alt="delete"></a></li>');
        //$('#email_list2').append('<li><a href="' + id + '"><img src="/static/admin/img/icon_deletelink.gif" alt="delete"></a> ' + label + '</li>');
        $('.list-fieldset').show();
    }

    function get_string(datastore) {
        var values = [];
        for (var i in datastore) {
            values.push(datastore[i]);
        }
        return values.join();
    }

    function setup_ajax(field, list, searchfield, url) {
        var datastore = {};
        if(field.val() != '') {
            //datastore = $.evalJSON(field.val())
            items = field.val().split(',');
            $.each(items, function(index, value) {
                datastore[value] = value;
            });
        }

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
            if($('#email_list_list li').length==0) {
                $('.list-fieldset').hide();
            }
            return false;
        });
    }

    function init_forms() {
        // build query if returning to search form with parameters
        if(document.location.search.length) {
            $('#id_qdr').trigger('change');
        }
    }

    // hide selected lists div when empty
    if($('#email_list_list li').length==0) {
        $('.list-fieldset').hide();
    }

    // setup inline help messages
    $(".defaultText").focus(function(srcc) {
        if ($(this).val() == $(this)[0].title)
        {
            $(this).removeClass("defaultTextActive");
            $(this).val("");
        }
    });

    $(".defaultText").blur(function() {
        if ($(this).val() == "")
        {
            $(this).addClass("defaultTextActive");
            $(this).val($(this)[0].title);
        }
    });

    $(".defaultText").blur();

    $("#advanced-search-form").submit(function() {
        $(".defaultText").each(function() {
        if($(this).val() == $(this)[0].title) {
            $(this).val("");
        }
        });
    });
    // end setup inline help

    $("#id_qdr").change(function() {
        if($(this).val()=="c") {
            $("#custom_date").show();
        } else {
            $("#id_start_date").val("");
            $("#id_end_date").val("");
            $("#custom_date").hide();
        }
    });

    setup_ajax($("#id_email_list"), $("#email_list_list"), $("#email_list_search"), "archive/ajax/list/");
    init_forms();
});
