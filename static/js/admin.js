/* admin.js */

$(function() {

    function init() {
    // SETUP KEY BINDING
        $('#result-list').bind("keydown", function(event) {
            var keyCode = event.keyCode || event.which,
                arrow = {up: 38, down: 40, left: 37, right: 39};
                enter = 13;
                space = 32;
            switch (keyCode) {
                case arrow.up:
                    event.preventDefault();
                    var row = $('.row-selected', this);
                    var prev = row.prev();
                    if(prev.length > 0) {
                        row.removeClass('row-selected');
                        prev.addClass('row-selected');
                    }
                break;
                case arrow.down:
                    event.preventDefault();
                    var row = $('.row-selected', this);
                    var next = row.next();
                    if(next.length > 0) {
                        row.removeClass('row-selected');
                        next.addClass('row-selected');
                    }
                break;
                case arrow.right:
                    event.preventDefault();
                    var row = $('.row-selected', this);
                    //row.hide("slide", {direction:"right"});
                    row.hide();
                break;
                case arrow.left:
                    event.preventDefault();
                    var row = $('.row-selected', this);
                    //row.hide("slide", {direction:"right"});
                    row.hide();
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
        });

        // SETUP DOUBLE CLICK MESSAGE
        $('#result-table tr').dblclick(function() {
            var url = $(this).find("td:nth-child(6)").html();
            window.open(url);
        });
    }

    /* auto select first item in result list */
    function select_first_msg() {
        var row = $('table#result-table tr:first');
        row.addClass('row-selected');
        //load_msg(row);
    }

    /* Select all link */
    $('#selectall').on('click', function () {
        $('.action-select').prop('checked', this.checked);
    });

    /* handle message select from list */
    $('table#result-table tr').click(function () {
        $('table#result-table tr').removeClass('row-selected');
        $(this).addClass('row-selected');
        //load_msg($(this));
    });

    init();
    select_first_msg();
});
