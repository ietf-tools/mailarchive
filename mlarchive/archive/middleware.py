from django.shortcuts import redirect


def legacy_redirect_middleware(get_response):
    def legacy_redirect(request):
        if request.COOKIES.get('isLegacyOn') == 'true':
            redirect('index.html')

        response = get_response(request)

        return response

    return legacy_redirect
