/* admin.js */


var mailarchAdmin = {
    
    spamModeActive: false,
    focusInSearchForm: false,
    subjectCol: 2,
    fromCol: 3,
    rowsToMove: $(),
    
    init: function() {
        mailarchAdmin.cacheDom();
        mailarchAdmin.bindEvents();
        mailarchAdmin.$adminResults.focus();
        mailarchAdmin.selectInitialMessage();
        $(document).keydown(mailarchAdmin.messageNav);
    },
        
    cacheDom: function() {
        mailarchAdmin.$adminSearchForm = $('#id_admin_form');
        mailarchAdmin.$adminResults = $('#admin-results');
        mailarchAdmin.$activeResultTable = $('.active .result-table');
        mailarchAdmin.$ResultTableRows = $('.result-table tr');
        mailarchAdmin.$selectAll = $('#selectall');
        mailarchAdmin.$viewPane = $('#admin-view-pane');
        mailarchAdmin.$spamToggle = $('#spam-toggle');
        mailarchAdmin.$spamTable = $('#spam-pane table');
        mailarchAdmin.$cleanTable = $('#clean-pane table');
        mailarchAdmin.$spamYesButton = $('#yes-move');
        mailarchAdmin.$spamNoButton = $('#no-move');
        mailarchAdmin.$spamProcessButton = $('#spam-process');
        mailarchAdmin.$tabContent = $('.tab-content');
    },
    
    bindEvents: function() {
        //mailarchAdmin.$resultTable.on('keydown', mailarchAdmin.messageNav);
        mailarchAdmin.$adminSearchForm.on('focusin', mailarchAdmin.focusInSearchFormOn);
        mailarchAdmin.$adminSearchForm.on('focusout', mailarchAdmin.focusInSearchFormOff);
        mailarchAdmin.$selectAll.on('click', mailarchAdmin.selectAll);
        mailarchAdmin.$ResultTableRows.on('click', mailarchAdmin.selectRowHandler);
        mailarchAdmin.$ResultTableRows.on('dblclick', mailarchAdmin.openMsg);
        mailarchAdmin.$spamToggle.on('click', mailarchAdmin.toggleSpam);
        mailarchAdmin.$spamYesButton.on('click', mailarchAdmin.moveRowsToSpam);
        mailarchAdmin.$spamNoButton.on('click', mailarchAdmin.moveSelectedToSpam);
        mailarchAdmin.$spamProcessButton.on('click', mailarchAdmin.processSpam);
        $( document ).ajaxStart(function() {
            $(".spinner").removeClass("d-none");
        });
        $( document ).ajaxStop(function() {
            $(".spinner").addClass("d-none");
        });
    },

    focusInSearchFormOn: function() {
        focusInSearchForm = true;
        console.log("focusInSearchForm:" + focusInSearchForm);
    },

    focusInSearchFormOff: function() {
        focusInSearchForm = false;
        console.log("focusInSearchForm:" + focusInSearchForm);
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
                // NOTE: don't use cached DOM objects here because these change
                $('#msg-header').hide();
                $('#msg-info').hide();
                $('#msg-body h3').hide();
            });
        }
    },
    
    messageNav: function(event) {
        var keyCode = event.keyCode || event.which,
            arrow = {up: 38, down: 40, left: 37, right: 39};
            enter = 13;
            space = 32;
        if (focusInSearchForm==true) {
            return true;
        }
        switch (keyCode) {
            case arrow.up:
                event.preventDefault();
                var row = $('.row-selected', this);
                var prev = row.prev();
                if(prev.length > 0) {
                    mailarchAdmin.selectRow(prev);
                    mailarchAdmin.scrollGrid(prev);
                }
            break;
            case arrow.down:
                event.preventDefault();
                var row = $('.row-selected', this);
                var next = row.next();
                if(next.length > 0) {
                    mailarchAdmin.selectRow(next);
                    mailarchAdmin.scrollGrid(next);
                }
            break;
            case arrow.right:
                event.preventDefault();
                if (mailarchAdmin.spamModeActive) {
                    event.preventDefault();
                    mailarchAdmin.moveToSpam();
                }
            break;
            case arrow.left:
                event.preventDefault();
                if (mailarchAdmin.spamModeActive) {
                    event.preventDefault();
                    mailarchAdmin.moveToClean();
                }
            break;
            case space:
                event.preventDefault();
                var row = $('.row-selected', this);
                var chkbx = $('.action-select',row);
                chkbx.prop('checked',!chkbx.prop('checked'));
            break;
            //case enter:
            //    var url = $('.row-selected', this).find("td:nth-child(6)").html();
            //    window.open(url);
            //break;
        }
    },
    
    moveRows: function(rows,target,direction) {
        var index = $(".row-selected").index();
        rows.each(function(index, value) {
            var tr = $(this);
            var clone = tr.clone(true).appendTo(target);
            clone.removeClass('row-selected');
            tr.remove();
            //tr.hide("slide", {direction:direction}, 300, mailarchAdmin.callback);
        })
        var row = $(".active tbody tr").eq(index);
        mailarchAdmin.selectRow(row);
        mailarchAdmin.refreshTabLabels();
    },

    callback: function() {
        $(this).remove();
    },

    moveToSpam: function() {
        // move selected row, if other rows match subject, prompt to move
        var tr = $('.row-selected');
        var subject = tr.find('td:eq('+mailarchAdmin.subjectCol+')').text();
        var rows = $('.active .result-table tbody tr');
        var matches = rows.filter(function() {
            return $(this).find('td:eq('+mailarchAdmin.subjectCol+')').text() === subject;
        })
        if(matches.length > 1 && !$("#move-subject").is(':checked')){
            mailarchAdmin.rowsToMove = matches;
            $('#spam-modal').modal('show');
        } else {
            mailarchAdmin.moveRows(matches, mailarchAdmin.$spamTable, "right");
        }
        
    },

    moveRowsToSpam: function() {
        mailarchAdmin.moveRows(mailarchAdmin.rowsToMove, mailarchAdmin.$spamTable, "right");
        mailarchAdmin.rowsToMove = $();
        $('#spam-modal').modal('hide');
    },

    moveSelectedToSpam: function() {
        mailarchAdmin.moveRows($('.row-selected'),mailarchAdmin.$spamTable, "right");
        mailarchAdmin.rowsToMove = $();
        $('#spam-modal').modal('hide');
    },

    moveToClean: function() {
        // move selected row and all with matching from address
        var tr = $('.row-selected');
        var from = tr.find('td:eq('+mailarchAdmin.fromCol+')').text();
        var rows = $('.active .result-table tbody tr');
        var matches = rows.filter(function() {
            return $(this).find('td:eq('+mailarchAdmin.fromCol+')').text() === from;
        })
        mailarchAdmin.moveRows(matches, mailarchAdmin.$cleanTable, "left");
    },

    openMesg: function() {
        var url = $(this).find("td:nth-child(6)").html();
        window.open(url);
    },

    processPane: function(pane, action){
        var data = new Object();
        var rows = pane.find(".result-table tbody tr");
        var ids = new Array();
        rows.each( function() {
            ids.push( $(this).find("td:last").html() );
        })
        data.action = action;
        data.ids = ids.join();
        data.csrfmiddlewaretoken = $.cookie("csrftoken");
        console.log(data);
        var jqxhr = $.post( "/arch/ajax/admin/action/", data, function() {
            //alert( "success" );
            rows.remove();
            mailarchAdmin.refreshTabLabels();
        })
        .done(function() {
            //alert( "second success" );
        })
        .fail(function() {
            alert( "error" );
        })
        .always(function() {
            //alert( "finished" );
        })
    },

    processSpam: function(){
        $(".spinner").removeClass("d-none");
        mailarchAdmin.processPane($("#spam-pane"), "remove_selected");
        mailarchAdmin.processPane($("#clean-pane"), "not_spam");
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

    // manage scroll bar
    scrollGrid: function (row){
        // changed formula because rpos is always within clientheight
        var ch = mailarchAdmin.$tabContent[0].clientHeight;
        var st = mailarchAdmin.$tabContent.scrollTop();
        var rtop = row.position().top;
        var xtop = mailarchAdmin.$tabContent.position().top;
        var xh = mailarchAdmin.$tabContent.height();
        var rh = row.height();
        if (rtop < (xtop+rh)) {
            mailarchAdmin.$tabContent.scrollTop(st-rh);
        } else if ((rtop+rh)>(xtop+xh)) {
            mailarchAdmin.$tabContent.scrollTop(st+rh);
        }
    },
    
    selectAll: function () {
        $('.active .action-select').prop('checked', this.checked);
    },
    
    selectInitialMessage: function() {
        if($('.active .result-table tr').length > 1) {
            mailarchAdmin.selectRow($('.active .result-table tr').eq(1));
        }
    },

    selectRow: function (row) {
        $('.result-table tr').removeClass('row-selected');
        row.addClass('row-selected');
        if (mailarchAdmin.spamModeActive){
            mailarchAdmin.loadMessage(row);
        }
    },

    selectRowHandler: function() {
        mailarchAdmin.selectRow($(this));
    },

    toggleSpam: function() {
        // NOTE the function gets called BEFORE state change
        if ($(this).hasClass('active')) {
            mailarchAdmin.spamModeActive = false;
            $('body').css('overflow', 'visible');
            $('.spam-top').addClass('d-none');
            mailarchAdmin.$viewPane.addClass('d-none');
            $('#admin_search_form').removeClass('d-none');
            mailarchAdmin.$spamProcessButton.addClass('disabled');
            $("#move-subject").parents('div.checkbox-inline').addClass('d-none');
            mailarchAdmin.$tabContent.removeClass('spam-mode');
        } else {
            mailarchAdmin.spamModeActive = true;
            $('body').css('overflow', 'd-none');
            $('.spam-top').removeClass('d-none');
            mailarchAdmin.$viewPane.removeClass('d-none');
            $('#admin_search_form').addClass('d-none');
            mailarchAdmin.$spamProcessButton.removeClass('disabled');
            mailarchAdmin.loadMessage($('.row-selected'));
            $("#move-subject").parents('div.checkbox-inline').removeClass('d-none');
            mailarchAdmin.$tabContent.addClass('spam-mode');
        }
    }
}


$(function() {
    mailarchAdmin.init();
});
