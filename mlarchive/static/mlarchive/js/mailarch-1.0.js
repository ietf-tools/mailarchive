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
    defaultListPaneHeight: 229,
    
    // PRIMARY FUNCTIONS =====================================
    
    init: function() {
        mailarch.cacheDom();
        mailarch.handleResize();
        mailarch.bindEvents();
        mailarch.progressiveFeatures();
        mailarch.initMessageList();
        mailarch.initFilters();
        mailarch.setLastItem();
        mailarch.getURLParams();
        mailarch.initSort();
    },

    cacheDom: function() {
        mailarch.$browseHeader = $('#browse-header');
        mailarch.$clearSort = $('#clear-sort');
        mailarch.$content = $('#content');
        mailarch.$filterPopups = $('.filter');
        mailarch.$filterOptions = $('input.facetchk[type=checkbox]');
        mailarch.$fromFilterClear = $('#from-filter-clear');
        mailarch.$fromFilterContainer = $('#from-filter-container');
        mailarch.$threadLink = $('#gbt-link');
        mailarch.$listFilterClear = $('#list-filter-clear');
        mailarch.$listFilterContainer = $('#list-filter-container');
        mailarch.$listPane = $("#list-pane");
        mailarch.$modifySearch = $('#modify-search');
        mailarch.$moreLinks = $('.more-link');
        mailarch.$msgList = $('.msg-list');
        mailarch.$msgTable = $('.msg-table');
        mailarch.$msgTableTbody = this.$msgTable.find('.xtbody');
        mailarch.$msgTableRows = this.$msgTable.find('.xtr');
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
        mailarch.$filterPopups.on('blur', mailarch.closeFilterPopup);
        mailarch.$filterOptions.on('change', mailarch.applyFilter);
        mailarch.$fromFilterClear.on('click', mailarch.clearFromFilter);
        mailarch.$threadLink.on('click', mailarch.groupByThread);
        mailarch.$listFilterClear.on('click', mailarch.clearListFilter);
        mailarch.$modifySearch.on('click', mailarch.removeIndexParam);
        mailarch.$moreLinks.on('click', mailarch.showFilterPopup);
        mailarch.$msgList.on('keydown', mailarch.messageNav);
        mailarch.$msgList.on('scroll', mailarch.infiniteScroll);
        mailarch.$msgTable.on('click','.xtr', mailarch.selectRow);
        mailarch.$msgTable.on('dblclick','.xtr', mailarch.gotoMessage);
        mailarch.$searchForm.on('submit', mailarch.submitSearch);
        mailarch.$sortButtons.on('click', mailarch.performSort);
        mailarch.$window.resize(mailarch.handleResize);
        if(!mailarch.isSmallViewport()) {
            mailarch.$window.on('scroll', mailarch.infiniteScroll);
        }
    },
    
    // SECONDARY FUNCTIONS ====================================
    
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
        var url = $(this).find(".xtd:nth-child(6)").html();
        window.open(url);
    },
    
    groupByThread: function(event) {
        event.preventDefault();
        if(mailarch.urlParams.hasOwnProperty('gbt')) {
            delete mailarch.urlParams.gbt;
        } else {
            mailarch.urlParams['gbt'] = '1';
        }
        // add index to URL to preserve context
        var path = mailarch.$msgTable.find('.xtr.row-selected .xtd:nth-child(6)').text();
        var parts = path.split('/');
        var hash = parts[parts.length - 1];
        mailarch.urlParams['index'] = hash;
        mailarch.doSearch();
    },

    handleResize: function() {
        if(mailarch.isSmallViewport()) {
            $('.header').removeAttr('style');
            $('#list-pane').removeAttr('style');
            mailarch.$window.off('scroll', mailarch.infiniteScroll);
        } else {
            mailarch.setHeaderWidths();
            mailarch.$window.on('scroll', mailarch.infiniteScroll);
        }
    },
    
    hasOverflow: function (element) {
        if(element.clientWidth < element.scrollWidth) {
            return true;
        } else {
            return false;
        }
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
                    mailarch.$msgTableTbody.append(data);
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
                    var lengthBefore = mailarch.$msgTable.find('.xtr').length;
                    mailarch.$msgTableTbody.prepend(data);
                    var numNewRows = mailarch.$msgTable.find('.xtr').length - lengthBefore;
                    var newOffset = firstItem - numNewRows;
                    mailarch.$msgList.data('queryset-offset',newOffset);
                    var oldTop = mailarch.$msgTable.find('.xtr').eq(numNewRows);
                    mailarch.$msgList.scrollTop(oldTop.position().top);
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
    
    initMessageList: function() {
        if (!mailarch.isSmallViewport()) {
            mailarch.$msgList.focus();
            mailarch.initSplitter();
            mailarch.selectInitialMessage();
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
            var icon = elem.find(".glyphicon");
            if(so.match("^-")){
                icon.removeClass().addClass("glyphicon glyphicon-sort-by-attributes-alt sort-active");
            } else {
                icon.removeClass().addClass("glyphicon glyphicon-sort-by-attributes sort-active");
            }
        }
    },
    
    initSplitter: function() {
        // no splitter for mobile
        if (mailarch.isSmallViewport()) {
            return true;
        }
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
            mailarch.setSplitter(mailarch.defaultListPaneHeight);  // optimize for 1024x768
        }
    },
    
    isSmallViewport: function() {
        if ($(window).width() <= 768) {
            return true;
        } else {
            return false;
        }
    },
    
    // given the row of the msg list, load the message text in the mag view pane
    loadMessage: function(row) {
        var msgId = row.find(".xtd:last").html();
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
            var row = mailarch.$msgTable.find('.xtr:eq(' + offset + ')');
            mailarch.$msgList.scrollTop(mailarch.$msgList.scrollTop() + row.position().top);
        } else {
            var row = mailarch.$msgTable.find('.xtbody .xtr:first');
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
        // synchronize the message list header columns with the scrollable content table
        if ($('.msg-table .xtd.no-results').length == 1 ||
            mailarch.hasOverflow(mailarch.$msgList[0])) {
                $('.header').removeAttr('style');
        } else {
            $(".header").each(function (i){
                $(this).width($($(".msg-table .xtr:first .xtd")[i]).width() + 16);
            });
        }
    },
    
    setLastItem: function() {
        var offset = mailarch.$msgList.data('queryset-offset');
        mailarch.lastItem = mailarch.$msgTable.find('.xtr').length + offset;
    },
    
    setSplitter: function(top) {
        // set page elements when splitter moves
        mailarch.$listPane.css("height",top-3);
        mailarch.$viewPane.css("top",top+3);
        mailarch.$splitterPane.css("top",top);
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
    //alert("Viewport: " + $( window ).height() + "Document: " + $( document ).height());
});

(function($) {
    $.fn.hasScrollBar = function() {
        return this.get(0).scrollHeight > this.height();
    }
})(jQuery);