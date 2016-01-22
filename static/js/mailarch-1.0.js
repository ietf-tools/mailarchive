/* search.js */

/*
This script uses the JQuery Query String Object plugin
http://archive.plugins.jquery.com/project/query-object
https://github.com/blairmitchelmore/jquery.plugins/blob/master/jquery.query.js
*/


var mailarch = {

    // VARAIBLES =============================================
    lastItem: 0,
    urlParams: {},
    sortDefault: new Array(),
    
    // PRIMARY FUNCTIONS =====================================
    
    init: function() {
        mailarch.cacheDom();
        mailarch.bindEvents();
        mailarch.setHeaderWidths();
        mailarch.initButtons();
        mailarch.progressiveFeatures();
        mailarch.$msgList.focus();
        mailarch.selectInitialMessage();
        mailarch.initFilters();
        mailarch.setLastItem();
        mailarch.initSplitter();
        mailarch.getURLParams();
        mailarch.initSort();
    },

    cacheDom: function() {
        mailarch.$browseHeader = $('#browse-header');
        mailarch.$clearSort = $('#clear-sort');
        mailarch.$content = $('#content');
        mailarch.$exportButton = $('#export-button');
        mailarch.$exportOptions = $('#export-options');
        mailarch.$filterPopups = $('.filter');
        mailarch.$filterOptions = $('input.facetchk[type=checkbox]');
        mailarch.$fromFilterClear = $('#from-filter-clear');
        mailarch.$fromFilterContainer = $('#from-filter-container');
        mailarch.$groupButton = $('#group-button');
        mailarch.$listFilterClear = $('#list-filter-clear');
        mailarch.$listFilterContainer = $('#list-filter-container');
        mailarch.$listPane = $("#list-pane");
        mailarch.$modifySearch = $('#modify-search');
        mailarch.$moreLinks = $('.more-link');
        mailarch.$msgList = $('#msg-list');
        mailarch.$msgListHeaderTable = $("#msg-list-header-table");
        mailarch.$msgTable = $('#msg-table');
        mailarch.$msgTableRows = this.$msgTable.find('tr');
        mailarch.$pageLinks = $('#page-links');
        mailarch.$q = $('#id_q');
        mailarch.$searchButton = $('#search-button');
        mailarch.$searchForm = $('#id_search_form');
        mailarch.$sortButtons = $('a.sortbutton');
        mailarch.$splitterPane = $('#splitter-pane');
        mailarch.$viewPane = $('#view-pane');
        mailarch.$window = $(window);
    },

    bindEvents: function() {
        mailarch.$clearSort.on('click', mailarch.resetSort);
        mailarch.$exportButton.on('click', mailarch.showExportMenu);
        mailarch.$exportOptions.on('blur', mailarch.hideExportMenu);
        mailarch.$filterPopups.on('blur', mailarch.closeFilterPopup);
        mailarch.$filterOptions.on('change', mailarch.applyFilter);
        mailarch.$fromFilterClear.on('click', mailarch.clearFromFilter);
        mailarch.$groupButton.on('click', mailarch.groupByThread);
        mailarch.$listFilterClear.on('click', mailarch.clearListFilter);
        mailarch.$modifySearch.on('click', mailarch.removeIndexParam);
        mailarch.$moreLinks.on('click', mailarch.showFilterPopup);
        mailarch.$msgList.on('keydown', mailarch.messageNav);
        mailarch.$msgList.on('scroll', mailarch.infiniteScroll);
        mailarch.$msgTable.on('click','tr', mailarch.selectRow);
        mailarch.$msgTable.on('dblclick','tr', mailarch.gotoMessage);
        mailarch.$searchForm.on('submit', mailarch.submitSearch);
        mailarch.$sortButtons.on('click', mailarch.performSort);
        mailarch.$window.on('resize', mailarch.setHeaderWidths);
    },
    
    // SECONDARY FUNCTIONS ===================================
    
    applyFilter: function() {
        var values = [];
        var name = $(this).attr('name');
        $("input[name=" + name + "][type=checkbox]:checked").each(function() {
            values.push($(this).val());
        });
        var value = values.join(',');
        mailarch.urlParams[name] = value;
        // remove index URL parameter
        delete mailarch.urlParams.index;
        mailarch.doSearch();
    },
    
    clearListFilter: function(event) {
        event.preventDefault();
        delete mailarch.urlParams.f_list;
        mailarch.doSearch();
    },
    
    clearFromFilter: function(event) {
        event.preventDefault();
        delete mailarch.urlParams.f_from;
        mailarch.doSearch();
    },
    
    closeFilterPopup: function() {
        // must use a timeout, or else list disappears before link gets activated
        var obj = $(this);
        window.setTimeout(function() {
            $(obj).removeClass('filter-popup');
            $('li.filter-option', obj).slice(6).hide();
        },500);
    },
    
    doSearch: function() {
        // reload page after changing some query parameters
        delete mailarch.urlParams.page
        location.search = $.param(mailarch.urlParams);
    },
    
    getURLParams: function() {
        var match;
        var pl = /\+/g;  // Regex for replacing addition symbol with a space
        var search = /([^&=]+)=?([^&]*)/g;
        decode = function (s) { return decodeURIComponent(s.replace(pl, " ")); };
        query  = window.location.search.substring(1);

        while (match = search.exec(query))
            mailarch.urlParams[decode(match[1])] = decode(match[2]);

        // delete blank keys
        for(var key in mailarch.urlParams){
            if (mailarch.urlParams.hasOwnProperty(key)) {
                if (!mailarch.urlParams[key])
                    delete mailarch.urlParams[key];
            }
        }
    },
    
    gotoMessage: function() {
        var url = $(this).find("td:nth-child(6)").html();
        window.open(url);
    },
    
    groupByThread: function() {
        // event.preventDefault();
        if(mailarch.urlParams.hasOwnProperty('gbt')) {
            delete mailarch.urlParams.gbt;
        } else {
            mailarch.urlParams['gbt'] = '1';
        }
        // add index to URL to preserve context
        var path = mailarch.$msgTable.find('tr.row-selected td:nth-child(6)').text();
        var parts = path.split('/');
        var hash = parts[parts.length - 1];
        mailarch.urlParams['index'] = hash;
        mailarch.doSearch();
    },
    
    hideExportMenu: function() {
        var myList = $(this)
        window.setTimeout(function() { $(myList).hide(); },500);
        //$(this).hide();   # need to use timeout or element hides before control triggered
    },

    infiniteScroll: function() {
        // BOTTOM OF SCROLL
        if($(this).scrollTop() + $(this).innerHeight() > $(this)[0].scrollHeight - 2) {
            var queryid = mailarch.$msgList.attr('data-queryid');
            var request = $.ajax({
                "type": "GET",
                "url": "/arch/ajax/messages/",
                "data": { "queryid": queryid, "lastitem": mailarch.lastItem }
            });
            request.done(function(data, testStatus, xhr) {
                if(xhr.status == 200){
                    $('#msg-table tbody').append(data);
                    mailarch.setLastItem();
                } else if(xhr.status == 204)  {
                    mailarch.$msgList.off( "scroll" );
                }
            });
            request.fail(function(xhr, textStatus, errorThrown) {
                if(xhr.status == 404){
                    // server returns a 404 when query has expired from cache
                    window.location.reload();
                }
            });
        }
        // TOP OF SCROLL
        if($(this).scrollTop() == 0 && mailarch.$msgList.data("queryset-offset")){
            var queryid = mailarch.$msgList.attr('data-queryid');
            var firstItem = mailarch.$msgList.data('queryset-offset');
            var request = $.ajax({
                "type": "GET",
                "url": "/arch/ajax/messages/",
                "data": { "queryid": queryid, "firstitem": firstItem }
            });
            request.done(function(data, testStatus, xhr) {
                if(xhr.status == 200){
                    // NOTE: when prepending data scrollTop stays at zero
                    // meaning user loses context, so we need to reposition
                    // scrollTop after prepend.
                    var lengthBefore = mailarch.$msgTable.find('tr').length;
                    mailarch.$msgTable.find('tbody').prepend(data);
                    var numNewRows = mailarch.$msgTable.find('tr').length - lengthBefore;
                    var newOffset = firstItem - numNewRows;
                    var rowHeight = mailarch.$msgTable.find('tr:eq(0)').height();
                    mailarch.$msgList.data('queryset-offset',newOffset);
                    mailarch.$msgList.scrollTop(numNewRows * rowHeight);
                } else if(xhr.status == 204)  {
                    mailarch.$msgList.off( "scroll" );
                }
            });
            request.fail(function(xhr, textStatus, errorThrown) {
                if(xhr.status == 404){
                    // server returns a 404 when query has expired from cache
                    window.location.reload();
                }
            });
        }
    },
    
    initButtons: function() {
        mailarch.$searchButton.button();
        mailarch.$exportButton.button({
            icons: {
                secondary: "ui-icon-triangle-1-s"
            }
        });
        mailarch.$groupButton.button();
        mailarch.$sortButtons.button();
    },
    
    initFilters: function() {
        // put checked items up top
        $($('li:has(:checked)').get().reverse()).each(function() {
            p = $(this).parent();
            elem = $(this).detach();
            p.prepend(elem);
        });
        
        // hide extra filter options
        $('.filter-options').each(function(){
            $('li.filter-option', this).slice(6).hide();
        });
        
        // hide clear links as needed
        if ($('input.list-facet[type=checkbox]:checked').length == 0) {
            mailarch.$listFilterClear.hide();
        }
        if ($('input.from-facet[type=checkbox]:checked').length == 0) {
            mailarch.$fromFilterClear.hide();
        }
    },
    
    initSort: function() {
        mailarch.sortDefault['date'] = '-date';
        mailarch.sortDefault['email_list'] = 'email_list';
        mailarch.sortDefault['frm'] = 'frm';
        mailarch.sortDefault['score'] = '-score';
        mailarch.sortDefault['subject'] = 'subject';
        
        so = $.query.get('so');
        if(!so){
            mailarch.$clearSort.hide();
        }
        
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
    },
    
    initSplitter: function() {
        mailarch.$splitterPane.draggable({
            axis:"y",
            //containment:"parent",
            containment: [0,200,0,$(document).height()-100],
            drag: function(event, ui){
                var top = ui.position.top;
                mailarch.$listPane.css("height",top-3);
                mailarch.$viewPane.css("top",top+3);
            },
            stop: function(event, ui){
                var top = ui.position.top;
                $.cookie("splitter",top);
            }
        });
        
        // check for saved setting
        var splitterValue = parseInt($.cookie("splitter"));
        if(splitterValue) {
            mailarch.setSplitter(splitterValue);
        } else {
            mailarch.setSplitter(175);  // optimize for 1024x768
        }
    },
    
    // given the row of the msg list, load the message text in the mag view pane
    loadMessage: function(row) {
        var msgId = row.find("td:last").html();
        if(/^\d+$/.test(msgId)){
            mailarch.$viewPane.load('/arch/ajax/msg/?id=' + msgId, function() {
                // NTOE: don't use cached DOM objects here because these change
                $('#msg-header').hide()
                $('#msg-date').after('<a id="toggle" href="#">Show header</a>');
                $('#toggle').click(function(ev) {
                    $('#msg-header').toggle();
                    $(this).html(($('#toggle').text() == 'Show header') ? 'Hide header' : 'Show header');
                });
                mailarch.$viewPane.scrollTop(0);    // should this be msg-body?
            });
        }
    },

    // up and down arrows navigate list of messages
    messageNav: function(event) {
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
                    mailarch.loadMessage(prev);
                    mailarch.scrollGrid(prev);
                }
            break;
            case arrow.down:
                event.preventDefault();
                var row = $('.row-selected', this);
                var next = row.next();
                if(next.length > 0) {
                    row.removeClass('row-selected');
                    next.addClass('row-selected');
                    mailarch.loadMessage(next);
                    mailarch.scrollGrid(next);
                }
            break;
        }
    },
    
    performSort: function() {
        var id = $(this).attr('id');
        var so = $.query.get('so');
        var new_so = "";
        col = id.replace('sort-button-','');
        if(so==col){
            new_so = "-" + col;
        }
        else if(so=="-" + col){
            new_so = col;
        }
        else {
            new_so = mailarch.sortDefault[col];
        }

        // if there already was a sort order and the new sort order is not just a reversal
        // of the previous sort, save it as the secondary sort order
        if(so!="" && so!=true){
            if(so.replace('-','') != new_so.replace('-','')) {
                mailarch.urlParams['so'] = new_so;
                mailarch.urlParams['sso'] = so;
            } else {
                mailarch.urlParams['so'] = new_so;
            }
        } else {
            mailarch.urlParams['so'] = new_so;
        }

        // if sorting by other than date remove index URL parameter
        if(mailarch.urlParams['so'].replace('-','') != "date"){
            delete mailarch.urlParams.index;
        }
        mailarch.doSearch();
    },
    
    progressiveFeatures: function() {
        // Progressive Javascript setup
        
        // hide page links in favor of infinite scroll
        mailarch.$pageLinks.hide();
    
        // show list and from filters
        mailarch.$listFilterContainer.show();
        mailarch.$fromFilterContainer.show();
    },
    
    removeIndexParam: function() {
        delete mailarch.urlParams.index;
    },
    
    resetSort: function() {
        // remove sort options (back to default)
        delete mailarch.urlParams.so;
        delete mailarch.urlParams.sso;
        mailarch.doSearch();
    },
    
    // manage scroll bar
    scrollGrid: function (row){
        // changed formula because rpos is always within clientheight
        var ch = mailarch.$msgList[0].clientHeight,
        st = mailarch.$msgList.scrollTop(),
        rpos = row.position().top,
        rh = row.height();
        if(rpos+rh >= ch) { mailarch.$msgList.scrollTop(rpos-(ch)+rh+st); }
        else if(rpos < 0) {
            mailarch.$msgList.scrollTop(st+rpos);
        }
    },
    
    // auto select first item in result list
    selectInitialMessage: function() {
        var offset = mailarch.$msgList.data('selected-offset');
        if(offset > 0){
            var row = mailarch.$msgTable.find('tr:eq(' + offset + ')');
            var height = mailarch.$msgTable.find('tr:eq(0)').height();
            mailarch.$msgList.scrollTop((offset-1)*height);
        } else {
            var row = mailarch.$msgTable.find('tr:first');
        }
        row.addClass('row-selected');
        mailarch.loadMessage(row);
    },
    
    selectRow: function() {
        mailarch.$msgTableRows.removeClass('row-selected');
        $(this).addClass('row-selected');
        mailarch.loadMessage($(this));
    },
    
    setHeaderWidths: function() {
        // synchronize the message list header table with the scrollable content table
        mailarch.$msgListHeaderTable.width(mailarch.$msgTable.width());
        if(mailarch.$msgTable.find("tr:first td").length != 1) {
            mailarch.$msgListHeaderTable.find("tr th").each(function (i){
                $(this).width($(mailarch.$msgTable.find("tr:first td")[i]).width() + 10);
            });
        }
        // stretch query box to fill toolbar
        var w = mailarch.$content.width() - mailarch.$browseHeader.width() - 500;
        mailarch.$q.width(w);
    },
    
    setLastItem: function() {
        var offset = mailarch.$msgList.data('queryset-offset');
        mailarch.lastItem = mailarch.$msgTable.find('tr').length + offset;
    },
    
    setSplitter: function(top) {
        // set page elements when splitter moves
        mailarch.$listPane.css("height",top-3);
        mailarch.$viewPane.css("top",top+3);
        mailarch.$splitterPane.css("top",top);
    },
    
    showExportMenu: function(event) {
        event.preventDefault();
        $(this).next('ul').show().focus();
    },
    
    showFilterPopup: function(event) {
        event.preventDefault();
        var container = $(this).parents('div:eq(0)')
        container.addClass('filter-popup').focus();
        $('li.filter-option', container).show();
    },
    
    submitSearch: function(event) {
        event.preventDefault();
        mailarch.urlParams['q'] = mailarch.$q.val();
        delete mailarch.urlParams.index;
        mailarch.doSearch();
    }
}


$(function() {
    mailarch.init();
});
