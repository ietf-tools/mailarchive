/* base.js */

var base = {

    // VARAIBLES =============================================
    isStaticOn: $.cookie('isStaticOn') == "true" ? true : false,

    // PRIMARY FUNCTIONS =====================================
    
    init: function() {
        base.cacheDom();
        base.bindEvents();
        base.initStatic();
    },

    cacheDom: function() {
        base.$toggleStaticLink = $('#toggle-static');
    },

    bindEvents: function() {
        base.$toggleStaticLink.on('click', base.toggleStatic);
    },

    initStatic: function() {
        if(base.isStaticOn) {
            base.$toggleStaticLink.text("Turn Static Mode Off");
        }
    },

    toggleStatic: function(event) {
        event.preventDefault();
        if(base.isStaticOn) {
            base.isStaticOn = false;
            $.cookie('isStaticOn','false', { expires: 5*365, path: '/'});
            base.$toggleStaticLink.text("Turn Static Mode On");
            if(typeof mailarch !== 'undefined'){
                mailarch.staticOff();
            }
            if(typeof mailarchDetails !== 'undefined'){
                mailarchDetails.staticOff();
            }
            if(typeof mailarchStaticIndex !== 'undefined'){
                mailarchStaticIndex.staticOff();
            }
        } else {
            base.isStaticOn = true;
            $.cookie('isStaticOn','true', { expires: 5*365, path: '/'});
            base.$toggleStaticLink.text(" Turn Static Mode Off");
            if(typeof mailarch !== 'undefined'){
                mailarch.staticOn();
            }
            if(typeof mailarchDetails !== 'undefined'){
                mailarchDetails.staticOn();
            }
        }
    },
}

$(function() {
    base.init();
});