/* search_advanced.js */

/*
This script controls the Adavanced Search Form.  It dynamically constructs the search
query string based on the contents of the various advanced search form widgets.
*/


var advancedSearch = {

    // PRIMARY FUNCTIONS =====================================
    
    init : function() {
        advancedSearch.cacheDom();
        advancedSearch.progressiveFeatures();
        advancedSearch.bindEvents();
        advancedSearch.$emailList.selectize();
        if(document.location.search.length) {
            advancedSearch.handleReturn();
        }
    },
    
    cacheDom : function() {
        advancedSearch.$addLinks = $('.addChunk');
        advancedSearch.$builtQuery = $('#built-query');
        advancedSearch.$dateFields = $('.date-fields');
        advancedSearch.$emailList = $('#id_email_list');
        advancedSearch.$endDate = $('#id_end_date');
        advancedSearch.$operands = $('input.operand');
        advancedSearch.$parameters = $('select.parameter');
        advancedSearch.$qdr = $('#id_qdr');
        advancedSearch.$qualifiers = $('select.qualifier');
        advancedSearch.$removeButtons = $('.btn-remove');
        advancedSearch.$rulesForm = $('.rules-form');
        advancedSearch.$startDate = $('#id_start_date');
    },
    
    bindEvents : function() {
        advancedSearch.$rulesForm.find('input').first().focus()
        advancedSearch.$operands.bind('change keyup',advancedSearch.buildQuery);
        advancedSearch.$parameters.change(advancedSearch.buildQuery);
        advancedSearch.$qualifiers.change(advancedSearch.handleQualifier);
        advancedSearch.$removeButtons.click(advancedSearch.removeChunk);
        advancedSearch.$addLinks.click(advancedSearch.addChunk);
        advancedSearch.$qdr.change(advancedSearch.qdrChange);
    },
    
    // SECONDARY FUNCTIONS ====================================
    
    addChunk : function() {
        var chunks = $(this).siblings('div');
        chunks.first().addClass('removable');
        var cloned = chunks.last().clone(true);
        cloned.insertAfter(chunks.last());
        advancedSearch.incrementIds(cloned);
    },
        
    buildQuery : function(ev) {
        var query_string='';
        // var op_value=$('#id_operator').val();

        // regular query fields'
        var operands=new Array();
        $('.chunk').each(function() {
            var value = $(this).find('input').val();
            if(value!=''){
                if($(this).find('select.qualifier').val()=='exact'){
                    value.replace('"','');
                }
                var obj={
                    param:$(this).find('select.parameter').val(),
                    keyword:value
                };
                operands.push(jQuery.substitute(advancedSearch.getPattern($(this)),obj))
            }
        });
        // query_string += operands.join(' '+op_value+' ');
        query_string += operands.join(' ');

        $('#id_q').val(query_string);
    },
    
    getPattern : function(el) {
        var default_pattern='({keyword})';
        var default_exact_pattern='"{keyword}"';
        var pattern;
        if(el.children('select.qualifier').val()=='exact'){
            pattern=default_exact_pattern;
        } else {
            pattern=default_pattern;
        }
        if(el.children('select.parameter').val()!=''){
            pattern='{param}:'+pattern;
        }
        if(el.hasClass('not_chunk')){
            pattern='-'+pattern;
        }
        return pattern
    },

    handleReturn : function() {
        // setup form when returning with query data
        $('.term-set').each(function() {
            if($(this).children('.chunk').length > 1) {
                $(this).children('.chunk').addClass('removable');
            }
        });

        advancedSearch.buildQuery();
        advancedSearch.$qdr.trigger('change');
    },
    
    handleQualifier : function(ev) {
        var field_id = $(ev.target).attr('id').replace('qualifier','field');
        if($(ev.target).val()=='startswith') {
            $("#" + field_id + " option").each(function() {
                var prefix = $(this).val().split("__");
                $(this).val(prefix[0] + "__startswith");
            });
        }
        else if($(ev.target).val()=='contains') {
            $("#" + field_id + " option").each(function() {
                var prefix = $(this).val().split("__");
                $(this).val(prefix[0]);
            });
        }
        //else if($(ev.target).val()=='exact') {
        //    $("#" + field_id + " option").each(function() {
        //       var prefix = $(this).val().split("__");
        //        $(this).val(prefix[0] + "__exact");
        //   });
        //}
        advancedSearch.buildQuery(ev);
    },
    
    incrementIds : function(el) {
        var from = $(el).attr('id').split('_')[2];
        var to = parseInt(from)+1;
        var old_id = $(el).attr("id");
        $(el).attr("id", old_id.replace(from, to));
        el.find('input,select').each(function() {
            var newName = $(this).attr('name').replace(from,to);
            var newId = $(this).attr('id').replace(from,to);
            $(this).attr({'name': newName, 'id': newId});
            if ( $(this).is('input') ) {
                $(this).val('');
            }
        });
        el.find('label').each(function() {
            var newFor = $(this).attr('for').replace(from,to);
            $(this).attr('for', newFor);
        });
    },
    
    progressiveFeatures: function() {
        // Progressive Javascript setup
        $('.js-show').show();
        $('.js-hide').hide();
        $('.js-hide input, .js-hide select').prop('disabled',true);
        advancedSearch.$dateFields.hide();
    },

    qdrChange : function() {
        if($(this).val()=='c') {
            advancedSearch.$dateFields.show();
        } else {
            advancedSearch.$startDate.val('');
            advancedSearch.$endDate.val('');
            advancedSearch.$dateFields.hide();
        }
    },

    removeChunk : function() {
        var chunk = $(this).closest('div');
        var siblings = chunk.siblings('div');
        chunk.remove();
        if (siblings.length == 1) {
            siblings.removeClass('removable');
        }
        advancedSearch.buildQuery();
    },

}

$(function() {
    jQuery.substitute = function(str, sub) {
        return str.replace(/\{(.+?)\}/g, function($0, $1) {
            return $1 in sub ? sub[$1] : $0;
        });
    };
    
    advancedSearch.init();

});
