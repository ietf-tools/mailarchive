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
    
    function getURLParameter(name) {
        return decodeURI(
            (RegExp(name + '=' + '(.+?)(&|$)').exec(location.search)||[,null])[1]
        );
    }

    function jump_to(label) {
        window.location="/archive/browse/" + label;
    }
    
    function sync_tables() {
        // synchronize the message list header table with the scrollable content table
        $("#msg-list-header-table").width($("#msg-table").width());
        if($('#msg-table').find("tr:first td").length != 1) {
            $("#msg-list-header-table tr th").each(function (i){
                $(this).width($($("#msg-table tr:first td")[i]).width() + 10);
            });
        }
    }
    
    function init_search() {
        sync_tables();
        $(window).resize(function(){
            sync_tables();
        });
        
        // init splitter
        $("#splitter-pane").draggable({
            axis:"y",
            //containment:"parent",
            containment: [0,200,0,$(document).height()-100],
            drag: function(event, ui){
                var top = ui.position.top;
                $("#list-pane").css("height",top-3);
                $("#view-pane").css("top",top+3);
            }
        });
        
        // optimize for 1024x768
        $("#list-pane").css("height",175);
        $("#view-pane").css("top",181);
        $("#splitter-pane").css("top",175);
        
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
            var url = $(this).find("td:nth-child(6)").html()
            window.open(url);
        });
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

    function setup_buttons() {
        // FILTERS =============================================
        $('.more-link').bind("click", function(event) {
            event.preventDefault();
            $(this).parent().next('div').show().focus();
        });
        $('.filter-extra-div').blur(function() {
            var myDiv = $(this)
            // must use a timeout, or else list disappears before link gets activated
            window.setTimeout(function() { $(myDiv).hide(); },500);
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
        var so=getURLParameter("so");
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
            location.search = $.query.set('so',new_so);
            // $('#id_so').val(new_so);
            // $('form#id_search_form').submit();
        });
        // show appropriate sort arrow icon
        if(so!='null'){
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
    }
    
    // given the row of the msg list, load the message text in the mag view pane
    function load_msg(row) {
        var msgId = row.find("td:last").html();
        /* TODO: this call needs auth */
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
