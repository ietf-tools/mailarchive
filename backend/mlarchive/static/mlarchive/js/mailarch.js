/* mailarch.js */

/*
This script uses the JQuery Query String Object plugin
http://archive.plugins.jquery.com/project/query-object
https://github.com/blairmitchelmore/jquery.plugins/blob/master/jquery.query.js
*/


var mailarch = {

    // VARAIBLES =============================================
    ajaxRequestSent: false,
    bottomMargin: 17,
    defaultListPaneHeight: 225,
    splitterTop: 225,   // set from cookie later
    isDateOrdered: false,
    isGroupByThread: false,
    showFilters: $.cookie('showfilters') == "false" ? false : true,
    showPreviewCookie: $.cookie('showpreview') == "false" ? false : true,
    lastItem: 0,
    urlParams: {},
    resultsPerPage: 20,
    sortDefault: new Array(),
    scrollMargin: $('.xtr').height(),
    splitterHeight: $('#splitter-pane').height(),
    timer_attempts: 300,
    smallViewport: false,
    
    // PRIMARY FUNCTIONS =====================================
    
    init: function() {
        mailarch.cacheDom();
        mailarch.setProps();
        mailarch.progressiveFeatures();
        mailarch.bindEvents();
        mailarch.initMessageList();
        mailarch.initSplitter();
        mailarch.initFilters();
        mailarch.initPanels();
        mailarch.initSort();
        mailarch.handleResize();
    },

    cacheDom: function() {
        mailarch.$browseHeader = $('#browse-header');
        mailarch.$clearSort = $('#clear-sort');
        mailarch.$content = $('#content');
        mailarch.$exportLinks = $('a.export-link');
        mailarch.$exportSpinner = $('.export-spinner');
        mailarch.$filterPopups = $('.filter');
        mailarch.$filterOptions = $('input.facetchk[type=checkbox]');
        mailarch.$fromFilterClear = $('#from-filter-clear');
        mailarch.$threadLink = $('#gbt-link');
        mailarch.$listFilterClear = $('#list-filter-clear');
        mailarch.$listPane = $("#list-pane");
        mailarch.$modifySearch = $('#modify-search');
        mailarch.$moreLinks = $('.more-link');
        mailarch.$msgLinks = $('a.msg-detail');
        mailarch.$msgList = $('.msg-list');
        mailarch.$msgListProgress = $('#msg-list-controls .progress');
        mailarch.$msgTable = $('.msg-table');
        mailarch.$msgTableTbody = this.$msgTable.find('.xtbody');
        mailarch.$pageCount = $('.page-nav .current-page');
        mailarch.$pageLinks = $('.page-nav a');
        mailarch.$q = $('#id_q');
        mailarch.$searchButton = $('#search-button');
        mailarch.$searchForm = $('#id_search_form');
        mailarch.$sidebar = $('#sidebar');
        mailarch.$sortButtons = $('a.sortbutton');
        mailarch.$splitterPane = $('#splitter-pane');
        mailarch.$toggleFiltersLink = $('#toggle-filters a');
        mailarch.$toggleFiltersIcon = $('#toggle-filters a i');
        mailarch.$togglePreviewLink = $('#toggle-preview a');
        mailarch.$togglePreviewIcon = $('#toggle-preview a i');
        mailarch.$viewPane = $('.view-pane');
        mailarch.$window = $(window);
    },

    bindEvents: function() {
        mailarch.$clearSort.on('click', mailarch.resetSort);
        mailarch.$exportLinks.on('click', mailarch.doExport);
        mailarch.$filterPopups.on('blur', mailarch.closeFilterPopup);
        mailarch.$filterOptions.on('change', mailarch.applyFilter);
        mailarch.$fromFilterClear.on('click', mailarch.clearFromFilter);
        mailarch.$threadLink.on('click', mailarch.groupByThread);
        mailarch.$listFilterClear.on('click', mailarch.clearListFilter);
        mailarch.$modifySearch.on('click', mailarch.removeIndexParam);
        mailarch.$moreLinks.on('click', mailarch.showFilterPopup);
        mailarch.$msgList.on('scroll', mailarch.infiniteScroll);
        mailarch.$searchForm.on('submit', mailarch.submitSearch);
        mailarch.$sortButtons.on('click', mailarch.performSort);
        mailarch.$toggleFiltersLink.on('click', mailarch.toggleFilters)
        mailarch.$togglePreviewLink.on('click', mailarch.togglePreview);
        mailarch.$window.resize(mailarch.handleResize);
        if(mailarch.showPreview){
            //mailarch.doShowPreview();
            mailarch.$msgList.on('keydown', mailarch.messageNav);
            mailarch.$msgTable.on('click','.xtr', mailarch.selectRow);
            mailarch.$msgTable.on('dblclick','.xtr', mailarch.gotoMessage);
        }
        if(!mailarch.isSmallViewport()) {
            mailarch.$window.on('scroll', mailarch.infiniteScroll);
        }
    },
    
    // SECONDARY FUNCTIONS ====================================
    
    addBorder: function(start, end) {
        return true;    // disabled for now
        // end is optional like slice
        if (mailarch.isDateOrdered && !mailarch.showPreview) {
            mailarch.ifChanged('date-col', 'date-border', start, end);
        }
        if (mailarch.isGroupByThread) {
            mailarch.ifChanged('thread-col', 'thread-border', start, end);
        }
    },

    ifChanged: function(field, border_class, start, end) {
        // make end argument optional to match slice arguments
        var range = Array.prototype.slice.call(arguments, 2, 4);
        var rowset = mailarch.$msgList.find(".xtr");
        var rows = rowset.slice.apply(rowset, range);
        
        var text = rows.first().find(".xtd." + field).text();
        rows.each(function( index ) {
            var val = $(this).find(".xtd." + field).text();
            if(val != text) {
                // console.log(index, val, text);
                $(this).addClass(border_class);
            }
            text = val;
        });
    },

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
    
    checkMessageListScrollBar: function() {
        // If listPane scroll bar is gone, see if there are more messages
        if(!mailarch.$msgList.hasScrollBar()) {
            alert("Scroll bar disappeared!")
        }
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
    
    copyUrlToClipboard: function() {
        // not used as of 2019-02-11
        var url = $('#msg-body').data('message-url');
        var el = document.createElement('textarea');
        el.value = url;
        // Set non-editable to avoid focus and move outside of view
        el.setAttribute('readonly', '');
        el.style = {position: 'absolute', left: '-9999px'};
        document.body.appendChild(el);
        // Select text inside element
        el.select();
        // Copy text to clipboard
        document.execCommand('copy');
        // Remove temporary element
        document.body.removeChild(el);
    },

    doSearch: function() {
        // reload page after changing some query parameters
        delete mailarch.urlParams.page;
        location.search = $.param(mailarch.urlParams);
    },
    
    getMaxListPaneHeight: function() {
        return $(window).height() - mailarch.$listPane.offset().top - mailarch.bottomMargin;
    },

    getNextMessages: function() {
        // prevent multiple requests
        if (mailarch.ajaxRequestSent) {
            return true;
        }
        var queryid = mailarch.$msgList.data('queryid');
        var browselist = mailarch.$msgList.data('browse-list');
        var referenceId = $("#msg-list .xtr:last .id-col").text();
        var data = $.extend({ "qid": queryid,
                     "referenceitem": mailarch.lastItem,
                     "browselist": browselist,
                     "referenceid": referenceId,
                     "direction": "next"
        }, mailarch.urlParams);
        var request = $.ajax({
            "type": "GET",
            "url": "/arch/ajax/messages/",
            "data": data
        });
        mailarch.ajaxRequestSent = true;
        mailarch.$msgListProgress.show();
        request.done(function(data, testStatus, xhr) {
            if(xhr.status == 200){
                var before = mailarch.$msgTableTbody.find(".xtr").length;
                mailarch.$msgTableTbody.append(data);
                mailarch.addBorder(before - 1);
                mailarch.setLastItem();

            } else if(xhr.status == 204)  {
                // mailarch.$msgList.off( "scroll" );
            }
        });
        request.fail(function(xhr, textStatus, errorThrown) {
            mailarch.ajaxRequestSent = false;
            if(xhr.status == 404){
                // server returns a 404 when query has expired from cache
                window.location.reload();
            }
        });
        request.always(function(data, testStatus, xhr) {
            mailarch.ajaxRequestSent = false;
            mailarch.$msgListProgress.hide();
        });
    },

    getPreviousMessages: function() {
        // prevent multiple requests
        if (mailarch.ajaxRequestSent) {
            return true;
        }
        var queryid = mailarch.$msgList.data('queryid');
        var referenceItem = mailarch.$msgList.data('queryset-offset');
        var browselist = mailarch.$msgList.data('browse-list');
        var referenceId = $("#msg-list .xtr:first .id-col").text();
        var data = $.extend({ "qid": queryid,
                     "referenceitem": referenceItem,
                     "browselist": browselist,
                     "referenceid": referenceId,
                     "direction": "previous"
        }, mailarch.urlParams);
        var request = $.ajax({
            "type": "GET",
            "url": "/arch/ajax/messages/",
            "data": data
        });
        mailarch.ajaxRequestSent = true;
        mailarch.$msgListProgress.show();
        request.done(function(data, testStatus, xhr) {
            if(xhr.status == 200){
                // NOTE: when prepending data scrollTop stays at zero
                // meaning user loses context, so we need to reposition
                // scrollTop after prepend.
                var lengthBefore = mailarch.$msgTable.find('.xtr').length;
                mailarch.$msgTableTbody.prepend(data);
                var numNewRows = mailarch.$msgTable.find('.xtr').length - lengthBefore;
                mailarch.addBorder(0, numNewRows + 1);
                var newOffset = referenceItem - numNewRows;
                mailarch.$msgList.data('queryset-offset',newOffset);
                var oldTop = mailarch.$msgTable.find('.xtr').eq(numNewRows);
                mailarch.$msgList.scrollTop(oldTop.position().top);
            } else if(xhr.status == 204)  {
                // mailarch.$msgList.off( "scroll" );
            }
        });
        request.fail(function(xhr, textStatus, errorThrown) {
            if(xhr.status == 404){
                // server returns a 404 when query has expired from cache
                window.location.reload();
            }
        });
        request.always(function(data, testStatus, xhr) {
            mailarch.ajaxRequestSent = false;
            mailarch.$msgListProgress.hide();
        });
    },

    getSplitterTop: function() {
        var top = parseInt($.cookie("splitter"));
        if(!top) {
            top = mailarch.defaultListPaneHeight;  // optimize for 1024x768
        }
        return top;
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
        var url = $(this).find(".xtd.url-col").html();
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
        var path = mailarch.$msgTable.find('.xtr.row-selected .xtd.url-col').text();
        var parts = path.split('/');
        var hash = parts[parts.length - 1];
        mailarch.urlParams['index'] = hash;
        mailarch.doSearch();
    },

    handleResize: function(event) {
        var isSmall = mailarch.isSmallViewport();
        // do these on any resize
        if(!isSmall){
            mailarch.setHeaderWidths();
        }
        if (typeof event == 'object') {
            // if we got an event, viewport size changed, check if went between large / small
            if(isSmall == mailarch.smallViewport){
                return true;
            } else {
                console.log("small:" + isSmall);
                mailarch.smallViewport = isSmall;
            }
        }
        // do these only if crossing the small screen width
        if(isSmall) {
            $('.header').removeAttr('style');
            $('#list-pane').removeAttr('style');
            mailarch.$window.off('scroll', mailarch.infiniteScroll);
            mailarch.$msgList.addClass('no-preview');
        } else {
            if(mailarch.showPreviewCookie){
                mailarch.$msgList.removeClass('no-preview');
            }
            mailarch.showPreview = mailarch.showPreviewCookie;
            mailarch.$window.on('scroll', mailarch.infiniteScroll);
            mailarch.setPaneHeights();
            if ($(".xtr").length == mailarch.resultsPerPage && !mailarch.$msgList.hasScrollBar()) {
                mailarch.getMessages();
            }
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
        if($(this).scrollTop() + $(this).innerHeight() > $(this)[0].scrollHeight - mailarch.scrollMargin) {
            mailarch.getNextMessages();
        }
        // TOP OF SCROLL
        if($(this).scrollTop() == 0 && mailarch.$msgList.data("queryset-offset")){
            mailarch.getPreviousMessages();
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
        if (!mailarch.isSmallViewport() && mailarch.showPreview) {
            mailarch.$msgList.focus();
            mailarch.selectInitialMessage();
        }
        mailarch.addBorder(0);
    },
    
    initPanels: function() {
        mailarch.setPaneHeights();
        if (!mailarch.showFilters) {
            mailarch.doHideFilters();
        }
        if (!mailarch.showPreview) {
            mailarch.doHidePreview(false);   // don't animate
        } else {
            mailarch.$msgList.removeClass('no-preview');
        }
    },

    initSort: function() {
        mailarch.sortDefault['date'] = 'date';
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
            var icon = elem.find(".fa");
            if(so.match("^-")){
                icon.removeClass().addClass("fa fa-sort-desc sort-active");
            } else {
                icon.removeClass().addClass("fa fa-sort-asc sort-active");
            }
        }
    },
    
    initSplitter: function() {
        // no splitter for mobile
        mailarch.splitterTop = mailarch.getSplitterTop();
        if (mailarch.isSmallViewport()) {
            return true;
        }
        mailarch.$splitterPane.draggable({
            axis:"y",
            //containment:"parent",
            containment: [0,200,0,$(window).height()-100],
            drag: function(event, ui){
                var top = ui.position.top;
                mailarch.$listPane.css("height",top);
                mailarch.$viewPane.css("top",top + mailarch.splitterHeight);
            },
            stop: function(event, ui){
                var top = ui.position.top;
                mailarch.splitterTop = top;
                $.cookie("splitter",top);
                // mailarch.checkMessageListScrollBar();
            }
        });
    },
    
    isSmallViewport: function() {
        if ($(window).width() <= 768) {
            return true;
        } else {
            return false;
        }
    },
    
/*
    staticOff: function() {
        if(!mailarch.showFilters){
            mailarch.toggleFilters();
        }
        if(!mailarch.showPreview){
            mailarch.togglePreview();
        }
        mailarch.$msgList.removeClass('static')
        mailarch.$msgList.on('keydown', mailarch.messageNav);
        mailarch.$msgTable.on('click','.xtr', mailarch.selectRow);
        mailarch.$msgTable.on('dblclick','.xtr', mailarch.gotoMessage);
        mailarch.initMessageList();
    },

    staticOn: function() {
        if(mailarch.showFilters){
            mailarch.toggleFilters();
        }
        if(mailarch.showPreview){
            mailarch.togglePreview();
        }
        mailarch.$msgList.addClass('static')
        mailarch.$msgList.off('keydown');
        mailarch.$msgTable.off('click','.xtr');
        mailarch.$msgTable.off('dblclick','.xtr');
        mailarch.$msgTable.find('.xtr').removeClass('row-selected');
        mailarch.addBorder(0);
    },
*/

    staticOff: function() {
        var staticOffUrl = mailarch.$msgList.data('static-off-url');
        if(staticOffUrl) {
            window.location.replace(staticOffUrl);
        }
    },

    staticOn: function() {
        var staticOnUrl = mailarch.$msgList.data('static-on-url');
        if(staticOnUrl) {
            window.location.replace(staticOnUrl);
        }
    },

    // given the row of the msg list, load the message text in the msg view pane
    loadMessage: function(row) {
        var msgId = row.find(".xtd.id-col").html();
        if(/^\d+$/.test(msgId)){
            mailarch.$viewPane.load('/arch/ajax/msg/?id=' + msgId, function() {
                // NTOE: don't use cached DOM objects here because these change
                $('#msg-date').after('<a id="toggle-msg-header" class="toggle" href="#">Show header</a>');
                $('#toggle-msg-header').click(function(ev) {
                    $('#msg-header').toggle();
                    $(this).html(($('#toggle-msg-header').text() == 'Show header') ? 'Hide header' : 'Show header');
                });
                var url = $('#msg-body').data('message-url');
                var html = '<a href="' + url + '" class="detail-link" title="Message Detail"><i class="fa fa-link fa-lg" aria-hidden="true"></i></a>'
                $('#msg-body').prepend(html);
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
        var col = id.replace('sort-button-','');
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
        mailarch.$pageLinks.addClass('btn btn-default d-xs-inline-block d-md-none');
        mailarch.$pageCount.addClass('d-xs-inline-block d-md-none');

        if(!mailarch.isSmallViewport() && mailarch.showPreview) {
            mailarch.$msgList.removeClass('no-preview');
        }
        
        // Show progressive elements
        $('.js-off').addClass('js-on').removeClass('js-off');

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
        if(rpos+rh >= ch) { 
            mailarch.$msgList.scrollTop(rpos-(ch)+rh+st); 
        } else if(rpos < 0) {
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
        if(!mailarch.showPreview) {
            row.find('a').focus();
        }
        mailarch.loadMessage(row);
    },
    
    selectRow: function() {
        mailarch.$msgTable.find('.xtr').removeClass('row-selected');
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
                // getBoundingClientRect returns full precision width of cell columns, then we round down,
                // otherwise rounding errors in Firefox / JQuery can cause the header row to wrap
                var width = Math.floor($(".msg-table .xtr:first .xtd")[i].getBoundingClientRect().width);
                $(this).width(width);
            });
        }
    },
    
    setLastItem: function() {
        var offset = mailarch.$msgList.data('queryset-offset');
        mailarch.lastItem = mailarch.$msgTable.find('.xtr').length + offset;
    },
    
    setPaneHeights: function() {
        mailarch.$viewPane.css("top",mailarch.splitterTop + mailarch.splitterHeight);
        mailarch.$splitterPane.css("top",mailarch.splitterTop);
        if(mailarch.showPreview) {
            mailarch.$listPane.css("height",mailarch.splitterTop);
        } else {
            mailarch.$listPane.css("height",mailarch.getMaxListPaneHeight());
        }
    },
    
    setProps: function() {
        mailarch.getURLParams();
        mailarch.setLastItem();
        mailarch.smallViewport = mailarch.isSmallViewport();
        mailarch.resultsPerPage = mailarch.$msgList.data('results-per-page');
        // get message ordering
        if(mailarch.urlParams.hasOwnProperty('gbt')) {
            mailarch.isDateOrdered = false;
            mailarch.isGroupByThread = true;
        } else if (!mailarch.urlParams.hasOwnProperty('so') || mailarch.urlParams['so'].endsWith('date')) {
            mailarch.isDateOrdered = true;
        }
        // override showPreview cookie if mobile (small screen)
        if(mailarch.smallViewport){
            mailarch.showPreview = false;
        } else {
            mailarch.showPreview = mailarch.showPreviewCookie;
        }
        //console.log(mailarch.isDateOrdered);
    },

    showFilterPopup: function(event) {
        event.preventDefault();
        var container = $(this).parents('div:eq(0)')
        container.addClass('filter-popup').focus();
        $('li.filter-option', container).show();
    },
    
    doExport: function(event) {
        $('.export-text').hide();
        mailarch.$exportSpinner.show();
        downloadToken = mailarch.$msgList.data('export-token');
        $(document.body).css({'cursor' : 'wait'});

        mailarch.downloadTimer = window.setInterval( function() {
            var token = $.cookie("downloadToken");
            if( (token == downloadToken) || (mailarch.timer_attempts == 0) ) {
                mailarch.exportDone();
            }
            mailarch.timer_attempts--;
        }, 1000 );

    },

    exportDone: function(event) {
        $(document.body).css({'cursor' : 'default'});
        window.clearInterval( mailarch.downloadTimer );
        $.removeCookie('downloadToken')
        mailarch.timer_attempts = 300;
        $('#export-modal').modal('toggle');
        $('.export-text').show();
        mailarch.$exportSpinner.hide();
    },

    submitSearch: function(event) {
        event.preventDefault();
        mailarch.urlParams['q'] = mailarch.$q.val();
        delete mailarch.urlParams.index;
        mailarch.doSearch();
    },
    
    toggleFilters: function(event) {
        event.preventDefault();
        if(mailarch.showFilters) {
            mailarch.doHideFilters();
        } else {
            mailarch.doShowFilters();
        }
    },

    doShowFilters: function() {
        mailarch.showFilters = true;
        $.cookie('showfilters','true');
        mailarch.$toggleFiltersIcon.addClass("fa-chevron-left");
        mailarch.$toggleFiltersIcon.removeClass("fa-chevron-right");
        mailarch.$sidebar.removeClass('d-none');
        $('#msg-components').removeClass('x-full-width');
        mailarch.setHeaderWidths();
    },

    doHideFilters: function() {
        mailarch.showFilters = false;
        $.cookie('showfilters','false');
        mailarch.$toggleFiltersIcon.removeClass("fa-chevron-left");
        mailarch.$toggleFiltersIcon.addClass("fa-chevron-right");
        mailarch.$sidebar.addClass('d-none');
        $('#msg-components').addClass('x-full-width');
        mailarch.setHeaderWidths();
    },

    togglePreview: function(event) {
        event.preventDefault();
        if(mailarch.showPreview) {
            mailarch.doHidePreview(event);
        } else {
            mailarch.doShowPreview(event);
        }
    },

    doShowPreview: function(event) {
        mailarch.showPreview = true;
        mailarch.showPreviewCookie = true;
        $.cookie('showpreview','true');
        mailarch.$togglePreviewIcon.addClass("fa-chevron-down");
        mailarch.$togglePreviewIcon.removeClass("fa-chevron-up");
        mailarch.$listPane.animate({height:mailarch.splitterTop},function() {
            mailarch.$viewPane.removeClass("d-none");
            mailarch.$splitterPane.removeClass("d-none");
            // mailarch.$viewPane.show();
            // mailarch.$splitterPane.show();
        });
        mailarch.$msgList.on('keydown', mailarch.messageNav);
        mailarch.$msgTable.on('click','.xtr', mailarch.selectRow);
        mailarch.$msgTable.on('dblclick','.xtr', mailarch.gotoMessage);
        mailarch.$msgList.removeClass('no-preview');
        mailarch.initMessageList();
    },

    doHidePreview: function(event) {
        var height = mailarch.getMaxListPaneHeight();
        mailarch.showPreview = false;
        mailarch.showPreviewCookie = false;
        $.cookie('showpreview','false');
        mailarch.$togglePreviewIcon.removeClass("fa-chevron-down");
        mailarch.$togglePreviewIcon.addClass("fa-chevron-up");
        //mailarch.$viewPane.hide();
        //mailarch.$splitterPane.hide();
        mailarch.$viewPane.addClass("d-none");
        mailarch.$splitterPane.addClass("d-none");
        if (event.type == 'click'){
            mailarch.$listPane.animate({height:height});
        } else {
            mailarch.$listPane.height(height);
        }
        mailarch.$msgList.off('keydown', mailarch.messageNav);
        mailarch.$msgTable.off('click','.xtr', mailarch.selectRow);
        mailarch.$msgTable.off('dblclick','.xtr', mailarch.gotoMessage);
        mailarch.$msgList.addClass('no-preview');
        mailarch.$msgTable.find('.xtr').removeClass('row-selected');
        mailarch.addBorder(0);
        //mailarch.handleResize();
    }
}


$(function() {
    $.cookie.defaults.path = '/';
    mailarch.init();
});

// Custom function to detect if vertical scroll bar is visible
(function($) {
    $.fn.hasScrollBar = function() {
        return this.get(0).scrollHeight > this.get(0).clientHeight;
    }
})(jQuery);