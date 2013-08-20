/* search.js */

/*
This script uses the JQuery Query String Object plugin
http://archive.plugins.jquery.com/project/query-object
*/

// GLOBAL VARIABLES
var sortDefault = new Array();
sortDefault['date'] = '-date';
sortDefault['email_list'] = 'email_list';
sortDefault['frm'] = 'frm';
sortDefault['score'] = '-score';
sortDefault['subject'] = 'subject';

$(function() {

    function add_to_list(list, id, label) {
        list.append('<li><a href="' + id + '"><img src="/static/admin/img/icon_deletelink.gif" alt="delete"></a> ' + label + '</li>');
    }

    function get_string(datastore) {
        var values = [];
        for (var i in datastore) {
            values.push(datastore[i]);
        }
        return values.join();
    }

    function set_widths() {
        // synchronize the message list header table with the scrollable content table
        $("#msg-list-header-table").width($("#msg-table").width());
        if($('#msg-table').find("tr:first td").length != 1) {
            $("#msg-list-header-table tr th").each(function (i){
                $(this).width($($("#msg-table tr:first td")[i]).width() + 10);
            });
        }
        // stretch query box to fill toolbar
        var w = $('#content').width() - $('#browse-header').width() - 500;
        $('#id_q').width(w);
    }

    function set_splitter(top) {
        // set page elements when splitter moves
        $("#list-pane").css("height",top-3);
        $("#view-pane").css("top",top+3);
        $("#splitter-pane").css("top",top);
    }

    function init_search() {
        set_widths();
        $(window).resize(function(){
            set_widths();
        });

        // init splitter ------------------------------------
        $("#splitter-pane").draggable({
            axis:"y",
            //containment:"parent",
            containment: [0,200,0,$(document).height()-100],
            drag: function(event, ui){
                var top = ui.position.top;
                $("#list-pane").css("height",top-3);
                $("#view-pane").css("top",top+3);
                $.cookie("splitter",top);
            }
        });

        // check for saved setting
        var splitterValue = parseInt($.cookie("splitter"));
        if(splitterValue) {
            set_splitter(splitterValue);
        } else {
            set_splitter(175);  // optimize for 1024x768
        }
        // end splitter ------------------------------------

        function scrGrid(row){
            // changed formula because rpos is always within clientheight
            var ch = $('#msg-list')[0].clientHeight,
            st = $('#msg-list').scrollTop(),
            rpos = row.position().top,
            rh = row.height();
            if(rpos+rh >= ch) { $('#msg-list').scrollTop(rpos-(ch)+rh+st); }
            else if(rpos < 0) {
                $('#msg-list').scrollTop(st+rpos);
            }
        }

        // SETUP KEY BINDING
        $('#msg-list').bind("keydown", function(event) {
            var keyCode = event.keyCode || event.which,
                arrow = {up: 38, down: 40 };
            switch (keyCode) {
                case arrow.up:
                    event.preventDefault();
                    var row = $('.row-selected', this);
                    var prev = row.prev();
                    if(prev.length > 0) {
                        row.removeClass('row-selected');
                        prev.addClass('row-selected');
                        load_msg(prev);
                        scrGrid(prev);
                    }
                break;
                case arrow.down:
                    event.preventDefault();
                    var row = $('.row-selected', this);
                    var next = row.next();
                    if(next.length > 0) {
                        row.removeClass('row-selected');
                        next.addClass('row-selected');
                        load_msg(next);
                        scrGrid(next);
                    }
                break;
            }
        });

        // set focus on msg-list pane
        $('#msg-list').focus();

        // SETUP DOUBLE CLICK MESSAGE
        $('#msg-table tr').dblclick(function() {
            var url = $(this).find("td:nth-child(6)").html();
            window.open(url);
        });
    }

    function setup_ajax_browse(field, list, searchfield, url) {
        searchfield.autocomplete({
            source: url,
            minLength: 1,
            select: function( event, ui ) {
                window.location="/archive/browse/" + ui.item.label;
                return false;
            }
        });
    }

    function setup_buttons() {
        // TOOLBAR =============================================
        $('#search-button').button();
        $('#export-button').button({
            icons: {
                secondary: "ui-icon-triangle-1-s"
            }
        });
        $('#radio').buttonset();
        // END TOOLBAR =========================================

        // FILTERS =============================================
        $('.filter').blur(function() {
            // must use a timeout, or else list disappears before link gets activated
            var obj = $(this);
            window.setTimeout(function() {
                $(obj).removeClass('filter-popup');
                $('li.filter-option', obj).slice(6).hide();
            },500);
        });
        // put checked items up top
        $($('li:has(:checked)').get().reverse()).each(function() {
            p = $(this).parent();
            elem = $(this).detach();
            p.prepend(elem);
        });
        $('.more-link').bind("click", function(event) {
            event.preventDefault();
            var container = $(this).parents('div:eq(0)')
            container.addClass('filter-popup').focus();
            $('li.filter-option', container).show();
        });
        // hide extra filter options
        $('.filter-options').each(function(){
            $('li.filter-option', this).slice(6).hide();
        });

        $('#list-filter-clear').bind("click", function(event) {
            event.preventDefault();
            location.search = $.query.set("f_list",'');
        });
        $('#from-filter-clear').bind("click", function(event) {
            event.preventDefault();
            location.search = $.query.set("f_from",'');
        });
        if ($('input.list-facet[type=checkbox]:checked').length == 0) {
            $('#list-filter-clear').hide();
        }
        if ($('input.from-facet[type=checkbox]:checked').length == 0) {
            $('#from-filter-clear').hide();
        }
        $('input.facetchk[type=checkbox]').change(function() {
            var values = [];
            var name = $(this).attr('name');
            $("input[name=" + name + "][type=checkbox]:checked").each(function() {
                values.push($(this).val());
            });
            var value = values.join(',');
            location.search = $.query.set(name,value);
        });
        // END FILTERS =========================================

        // SORTING =============================================
        $('a.sortbutton').button();
        var so = $.query.get('so');
        var new_so = "";
        $('a.sortbutton').click(function() {
            var id = $(this).attr('id');
            col = id.replace('sort-button-','');
            if(so==col){
                new_so = "-" + col;
            }
            else if(so=="-" + col){
                new_so = col;
            }
            else {
                new_so = sortDefault[col];
            }

            // if there already was a sort order and the new sort order is not just a reversal
            // of the previous sort, save it as the secondary sort order
            if(so!="" && so!=true){
                if(so.replace('-','') != new_so.replace('-','')) {
                    var query = $.query.set('so',new_so).set('sso',so);
                } else {
                    var query = $.query.set('so',new_so);
                }
            } else {
                var query = $.query.set('so',new_so);
            }
            location.search = query;
        });
        // show appropriate sort arrow icon
        if(so && so!=true){
            var col = so.replace('-','');
            var elem = $("#sort-button-" + col);
            if(so.match("^-")){
                icon = "ui-icon-triangle-1-s";
            } else {
                icon = "ui-icon-triangle-1-n";
            }
            elem.button({
                icons: {
                    secondary: icon
                }
            });
        }
        // END SORTING =========================================

        // EXPORT ==============================================
        $('#export-button').bind("click", function(event) {
            event.preventDefault();
            $(this).next('ul').show().focus();
        });
        $('ul#export-options').blur(function() {
            var myList = $(this)
            window.setTimeout(function() { $(myList).hide(); },500);
            //$(this).hide();   # need to use timeout or element hides before control triggered
        });
        // END EXPORT ==========================================
    }

    // given the row of the msg list, load the message text in the mag view pane
    function load_msg(row) {
        var msgId = row.find("td:last").html();
        /* TODO: this call needs auth */
        if(/^\d+$/.test(msgId)){
            $('#view-pane').load('/archive/ajax/msg/?id=' + msgId, function() {
                $('#msg-header').hide()
                $('#msg-date').after('<a id="toggle" href="#">Show header</a>');
                $('#toggle').click(function(ev) {
                    $('#msg-header').toggle();
                    $(this).html(($('#toggle').text() == 'Show header') ? 'Hide header' : 'Show header');
                });
                $('#view-pane').scrollTop(0);    // should this be msg-body?
            });
        }
    }

    /* auto select first item in result list */
    function select_first_msg() {
        var row = $('table#msg-table tr:first');
        row.addClass('row-selected');
        load_msg(row);
    }

    /* handle message select from list */
    $('table#msg-table tr').click(function () {
        $('table#msg-table tr').removeClass('row-selected');
        $(this).addClass('row-selected');
        load_msg($(this));
    });

    setup_buttons();
    init_search();
    select_first_msg();
});
