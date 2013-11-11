/* search.js */

/*
This script uses the JQuery Query String Object plugin
http://archive.plugins.jquery.com/project/query-object
https://github.com/blairmitchelmore/jquery.plugins/blob/master/jquery.query.js
*/

// GLOBAL VARIABLES
var lastItem = $('#msg-table tr').length;
var urlParams;
var sortDefault = new Array();
sortDefault['date'] = '-date';
sortDefault['email_list'] = 'email_list';
sortDefault['frm'] = 'frm';
sortDefault['score'] = '-score';
sortDefault['subject'] = 'subject';

$(function() {

    // HELPER FUNCTIONS =====================================

    function do_search() {
        // reload page after changing some query parameters
        delete urlParams.page
        location.search = $.param(urlParams);
    }

    function add_messages(data,textStatus,jqXHR) {
        // append new messages to end of results list table
        $('#msg-table tbody').append(data);
        lastItem = $('#msg-table tr').length;
    }

    function init_search() {
        // search results header widths ---------------------
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

        // SETUP KEY BINDING
        // up and down arrows navigate list of messages
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

        // handle message select from list (use handler delegation)
        $('#msg-table').on('click','tr',function () {
            $('table#msg-table tr').removeClass('row-selected');
            $(this).addClass('row-selected');
            load_msg($(this));
        });

        // SETUP DOUBLE CLICK MESSAGE
        $('#msg-table').on('dblclick','tr',function() {
            var url = $(this).find("td:nth-child(6)").html();
            window.open(url);
        });

        // SEARCH SUBMIT
        $('#id_search_form').submit(function(event) {
            event.preventDefault();
            urlParams['q'] = $('#id_q').val();
            do_search();
        });

        // GET URL PARAMETERS
        var match;
        var pl = /\+/g;  // Regex for replacing addition symbol with a space
        var search = /([^&=]+)=?([^&]*)/g;
        decode = function (s) { return decodeURIComponent(s.replace(pl, " ")); };
        query  = window.location.search.substring(1);

        urlParams = {};
        while (match = search.exec(query))
            urlParams[decode(match[1])] = decode(match[2]);

        // delete blank keys
        for(var key in urlParams){
            if (urlParams.hasOwnProperty(key)) {
                if (!urlParams[key])
                    delete urlParams[key];
            }
        }

        // INFINTE SCROLL
        $("#msg-list").on( "scroll", function() {
            if($(this).scrollTop() + $(this).innerHeight() == $(this)[0].scrollHeight) {
                var queryid = $('#msg-list').attr('data-queryid');
                var request = $.ajax({
                    "type": "GET",
                    "url": "/archive/ajax/messages/",
                    "data": { "queryid": queryid, "lastitem": lastItem }
                });
                request.done(function(data, testStatus, xhr) {
                    if(xhr.status == 200){
                        $('#msg-table tbody').append(data);
                        lastItem = $('#msg-table tr').length;
                    } else if(xhr.status == 204)  {
                        $("#msg-list").off( "scroll" );
                    }
                });
                request.fail(function(xhr, textStatus, errorThrown) {
                    if(xhr.status == 404){
                        // server returns a 404 when query has expired from cache
                        window.location.reload();
                    }
                });
            }
        });

    }

    // given the row of the msg list, load the message text in the mag view pane
    function load_msg(row) {
        var msgId = row.find("td:last").html();
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

    function reset_sort(){
        // remove sort options (back to default)
        delete urlParams.so;
        delete urlParams.sso;
        do_search();
    }

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

    // auto select first item in result list
    function select_first_msg() {
        var row = $('table#msg-table tr:first');
        row.addClass('row-selected');
        load_msg(row);
    }

    function set_splitter(top) {
        // set page elements when splitter moves
        $("#list-pane").css("height",top-3);
        $("#view-pane").css("top",top+3);
        $("#splitter-pane").css("top",top);
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

    function setup_buttons() {
        // TOOLBAR =============================================
        $('#search-button').button();
        $('#export-button').button({
            icons: {
                secondary: "ui-icon-triangle-1-s"
            }
        });
        $('#group-button').button();
        $('#group-button').click(function() {
            // event.preventDefault();
            if(urlParams.hasOwnProperty('gbt')) {
                delete urlParams.gbt;
            } else {
                urlParams['gbt'] = '1';
            }
            do_search();
        });
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
            delete urlParams.f_list;
            do_search();
        });
        $('#from-filter-clear').bind("click", function(event) {
            event.preventDefault();
            delete urlParams.f_from;
            do_search();
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
            urlParams[name] = value;
            do_search();
        });
        // END FILTERS =========================================

        // SORTING =============================================
        $('#clear-sort').click(function() {
            reset_sort();
        });
        $('a.sortbutton').button();
        var so = $.query.get('so');
        if(!so){
            $('#clear-sort').hide();
        }
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
                    urlParams['so'] = new_so;
                    urlParams['sso'] = so;
                } else {
                    urlParams['so'] = new_so;
                }
            } else {
                urlParams['so'] = new_so;
            }
            do_search();
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

    // END HELPER FUNCTIONS ====================================

    setup_buttons();
    init_search();
    select_first_msg();
});
