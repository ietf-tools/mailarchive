/* admin.js */


var mailarchAdmin = {

    init: function() {
        mailarchAdmin.cacheDom();
        mailarchAdmin.bindEvents();
        //mailarchAdmin.initButtons();
        mailarchAdmin.$adminResults.focus();
        mailarchAdmin.selectInitialMessage();
        //$(document).keydown(mailarchAdmin.messageNav);
    },

    cacheDom: function() {
        mailarchAdmin.$adminResults = $('#admin-results');
        mailarchAdmin.$resultTableRows = $('#result-table tr');
        mailarchAdmin.$selectAll = $('#selectall');
        mailarchAdmin.$viewPane = $('#admin-view-pane');
    },
    
    bindEvents: function() {
        mailarchAdmin.$adminResults.on('keydown', mailarchAdmin.messageNav);
        mailarchAdmin.$selectAll.on('click', mailarchAdmin.selectAll);
        mailarchAdmin.$resultTableRows.on('click', mailarchAdmin.selectRow);
        mailarchAdmin.$resultTableRows.on('dblclick', mailarchAdmin.openMsg);
    },

    doAction: function(row) {
        // perform selected action on row
        var action = $('select[name="action"]').val()
        alert("got here: " + action );
        if(action){
            var url = '/arch/ajax/admin/action';
            var id = row.find('td:last').text()
            data = { action: action, id: id }
            alert("and here " + data);
            $.get(url,data,mailarchAdmin.remove_row(row));
        }
    },
    
    // given the row of the msg list, load the message text in the mag view pane
    loadMessage: function(row) {
        var msgId = row.find("td:last").html();
        if(/^\d+$/.test(msgId)){
            mailarchAdmin.$viewPane.load('/arch/ajax/msg/?id=' + msgId, function() {
                // NTOE: don't use cached DOM objects here because these change
                $('#msg-header').hide();
                $('#msg-date').after('<a id="toggle" href="#">Show header</a>');
                $('#toggle').click(function(ev) {
                    $('#msg-header').toggle();
                    $(this).html(($('#toggle').text() == 'Show header') ? 'Hide header' : 'Show header');
                });
                //mailarchAdmin.$viewPane.scrollTop(0);    // should this be msg-body?
                // hide message link in this view
                $('#msg-link').hide();
            });
        }
    },
    
    messageNav: function(event) {
        var keyCode = event.keyCode || event.which,
            arrow = {up: 38, down: 40, left: 37, right: 39};
            enter = 13;
            space = 32;
        switch (keyCode) {
            case arrow.up:
                event.preventDefault();
                var row = $('.row-selected', this);
                var prev = row.prev();
                if(prev.find('th').length == 0) {
                    row.removeClass('row-selected');
                    prev.addClass('row-selected');
                    mailarchAdmin.loadMessage(prev);
                    mailarchAdmin.scrollGrid(prev);
                }
            break;
            case arrow.down:
                event.preventDefault();
                var row = $('.row-selected', this);
                var next = row.next();
                if(next.length > 0) {
                    row.removeClass('row-selected');
                    next.addClass('row-selected');
                    mailarchAdmin.loadMessage(next);
                    mailarchAdmin.scrollGrid(next);
                }
            break;
            //case arrow.right:
            //    event.preventDefault();
            //    var row = $('.row-selected', this);
            //    mailarchAdmin.doAction(row);
            //break;
            //case arrow.left:
            //    event.preventDefault();
            //    var row = $('.row-selected', this);
            //    //row.hide("slide", {direction:"right"});
            //    row.hide();
            //break;
            case space:
                var row = $('.row-selected', this);
                var chkbx = $('.action-select',row);
                chkbx.prop('checked',!chkbx.prop('checked'));
            break;
            case enter:
                var url = $('.row-selected', this).find("td:nth-child(6)").html();
                window.open(url);
            break;
        }
    },
    
    remove_row: function(row) {
        //row.hide("slide", {direction:"right"});
        row.hide();
    },
    
    selectInitialMessage: function() {
        if(mailarchAdmin.$resultTableRows.length > 1) {
            var row = mailarchAdmin.$resultTableRows.eq(1);
            row.addClass('row-selected');
            mailarchAdmin.loadMessage(row);
        }
    },
    
    openMesg: function() {
        var url = $(this).find("td:nth-child(6)").html();
        window.open(url);
    },
    
    // manage scroll bar
    scrollGrid: function (row){
        // changed formula because rpos is always within clientheight
        var ch = mailarchAdmin.$adminResults[0].clientHeight,
        st = mailarchAdmin.$adminResults.scrollTop(),
        rpos = row.position().top,
        rh = row.height();
        if(rpos+rh >= ch) { mailarchAdmin.$adminResults.scrollTop(rpos-(ch)+rh+st); }
        else if(rpos < 0) {
            mailarchAdmin.$adminResults.scrollTop(st+rpos);
        }
    },
    
    selectAll: function () {
        $('.action-select').prop('checked', this.checked);
    },
    
    selectRow: function () {
        mailarchAdmin.$resultTableRows.removeClass('row-selected');
        $(this).addClass('row-selected');
        mailarchAdmin.loadMessage($(this));
    },
}


$(function() {
    mailarchAdmin.init();
});