/* admin.js */


var mailarchAdmin = {
    
    spamModeActive: false,
    subjectCol: 2,
    fromCol: 3,
    rowsToMove: $(),
    
    init: function() {
        mailarchAdmin.cacheDom();
        mailarchAdmin.bindEvents();
        mailarchAdmin.$adminResults.focus();
        mailarchAdmin.selectInitialMessage();
        //$(document).keydown(mailarchAdmin.messageNav);
        $('#id_email_list').selectize({maxOptions:2000});
    },
        
    cacheDom: function() {
        mailarchAdmin.$adminResults = $('#admin-results');
        mailarchAdmin.$activeResultTable = $('.active .result-table');
        mailarchAdmin.$activeResultTableRows = $('.active .result-table tr');
        mailarchAdmin.$selectAll = $('#selectall');
        mailarchAdmin.$viewPane = $('#admin-view-pane');
        mailarchAdmin.$spamToggle = $('#spam-toggle');
        mailarchAdmin.$spamTable = $('#spam-pane table');
        mailarchAdmin.$cleanTable = $('#clean-pane table');
        mailarchAdmin.$spamYesButton = $('#yes-move');
        mailarchAdmin.$spamNoButton = $('#no-move');
    },
    
    bindEvents: function() {
        //mailarchAdmin.$resultTable.on('keydown', mailarchAdmin.messageNav);
        mailarchAdmin.$selectAll.on('click', mailarchAdmin.selectAll);
        mailarchAdmin.$activeResultTableRows.on('click', mailarchAdmin.selectRow);
        mailarchAdmin.$activeResultTableRows.on('dblclick', mailarchAdmin.openMsg);
        mailarchAdmin.$spamToggle.on('click', mailarchAdmin.toggleSpam);
        mailarchAdmin.$spamYesButton.on('click', mailarchAdmin.moveRowsToSpam);
        mailarchAdmin.$spamNoButton.on('click', mailarchAdmin.moveSelectedToSpam);
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
            $.get(url,data,mailarchAdmin.removeRow(row));
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
                    //mailarchAdmin.loadMessage(prev);
                    //mailarchAdmin.scrollGrid(prev);
                }
            break;
            case arrow.down:
                event.preventDefault();
                var row = $('.row-selected', this);
                var next = row.next();
                if(next.length > 0) {
                    row.removeClass('row-selected');
                    next.addClass('row-selected');
                    //mailarchAdmin.loadMessage(next);
                    //mailarchAdmin.scrollGrid(next);
                }
            break;
            case arrow.right:
                if (mailarchAdmin.spamModeActive) {
                    event.preventDefault();
                    mailarchAdmin.moveToSpam();
                }
            break;
            case arrow.left:
                if (mailarchAdmin.spamModeActive) {
                    event.preventDefault();
                    mailarchAdmin.moveToClean();
                }
            break;
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
    
    moveRows: function(rows,target) {
        rows.each(function() {
            var tr = $( this ).remove().clone();
            target.append(tr);
        })
        $('tr.row-selected').removeClass('row-selected');
        mailarchAdmin.selectInitialMessage();
        mailarchAdmin.refreshTabLabels();
    },

    moveToSpam: function() {
        // move selected row, if other rows match subject, prompt to move
        var tr = $('.row-selected');
        var subject = tr.find('td:eq('+mailarchAdmin.subjectCol+')').text();
        var rows = $('.active .result-table tr');
        var matches = rows.filter(function() {
            return $(this).find('td:eq('+mailarchAdmin.subjectCol+')').text() === subject;
        })
        if(matches.length > 1){
            mailarchAdmin.rowsToMove = matches;
            $('#spam-modal').modal('show');
        } else {
            mailarchAdmin.moveRows(tr, mailarchAdmin.$spamTable);
        }
        
    },

    moveRowsToSpam: function() {
        mailarchAdmin.moveRows(mailarchAdmin.rowsToMove, mailarchAdmin.$spamTable);
        mailarchAdmin.rowsToMove = $();
        $('#spam-modal').modal('hide');
    },

    moveSelectedToSpam: function() {
        mailarchAdmin.moveRows($('.row-selected'),mailarchAdmin.$spamTable);
        mailarchAdmin.rowsToMove = $();
        $('#spam-modal').modal('hide');
    },

    moveToClean: function() {
        // move selected row and all with matching from address
        var tr = $('.row-selected');
        var from = tr.find('td:eq('+mailarchAdmin.fromCol+')').text();
        var rows = $('.active .result-table tr');
        var matches = rows.filter(function() {
            return $(this).find('td:eq('+mailarchAdmin.fromCol+')').text() === from;
        })
        mailarchAdmin.moveRows(matches, mailarchAdmin.$cleanTable);
    },

    refreshTabLabels: function() {
        $('.nav-tabs li a').each( function(){
            var href = $(this).attr('href');
            var count = $(href).find('tbody tr').length;
            var text = $(this).text();
            var match = text.match(/\d+/);
            $(this).text(text.replace(match,count));
        })
    },

    removeRow: function(row) {
        //row.hide("slide", {direction:"right"});
        row.hide();
    },
    
    selectInitialMessage: function() {
        if($('.active .result-table tr').length > 1) {
            var row = $('.active .result-table tr').eq(1);
            row.addClass('row-selected');
            // mailarchAdmin.loadMessage(row);
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
        $('.active .action-select').prop('checked', this.checked);
    },
    
    selectRow: function () {
        mailarchAdmin.$activeResultTableRows.removeClass('row-selected');
        $(this).addClass('row-selected');
        mailarchAdmin.loadMessage($(this));
    },

    toggleSpam: function() {
        // NOTE the function gets called BEFORE state change
        if ($(this).hasClass('active')) {
            mailarchAdmin.spamModeActive = false;
            $('body').css('overflow', 'visible');
            $('ul.nav-tabs').addClass('hidden')
        } else {
            mailarchAdmin.spamModeActive = true;
            $('body').css('overflow', 'hidden');
            $(document).keydown(mailarchAdmin.messageNav);
            $('ul.nav-tabs').removeClass('hidden')
        }
    }
}


$(function() {
    mailarchAdmin.init();
});
