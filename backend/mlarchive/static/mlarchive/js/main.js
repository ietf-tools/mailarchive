$(function() {
    $('#id_q').focus();

    var source = [];
    var lists = [];
    var list_data = $("#id_search_form").data("lists");
    if (list_data) {
        lists = list_data.split(",");
    }
    $.each(lists, function(index, value) {
      var item = new Object();
      item.id = index;
      item.name = value;
      source.push(item);
    })

    var $input = $(".typeahead");
    $input.typeahead({
      source: source,
      autoSelect: false
    });
    $input.change(function() {
      var current = $input.typeahead("getActive");
      if (current) {
        // Some item from your model is active!
        if (current.name == $input.val()) {
          // This means the exact match is found. Use toLowerCase() if you want case insensitive match.
        } else {
          // This means it is only a partial match, you can either add a new item
          // or take the active if you don't want new items
        }
      } else {
        // Nothing is active so it is a new value (or maybe empty value)
      }
    });
    
    // $('.footer').after(screen.width);
});