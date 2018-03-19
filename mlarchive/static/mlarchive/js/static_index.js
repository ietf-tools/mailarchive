
var mailarchStaticIndex = {
    legacyOff: function() {
        var pathname = window.location.pathname; 
        var parts = pathname.split('/');
        var url = '/' + parts.slice(1,-1).join('/');
        window.location.replace(url);
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

