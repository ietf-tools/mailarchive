
var mailarchStaticIndex = {
    staticOff: function() {
        var staticOffUrl = $('.static-index').data('static-off-url');
        if(staticOffUrl) {
            window.location.replace(staticOffUrl);
        }
    },
}

// add scroll offset to fragment target (if there is one)
function delayedFragmentTargetOffset(){
    var offset = $(':target').offset();
    if(offset){
        // console.log("doing scroll");
        var scrollto = offset.top - 95; // minus fixed header height
        $('html, body').animate({scrollTop:scrollto}, 0);
        $(':target').focus();
    }
}

$(function() {
    setTimeout(delayedFragmentTargetOffset, 500);
});

