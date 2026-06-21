from django.shortcuts import redirect
from functools import wraps

def student_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('student_id'):
            return redirect('/student/login/')
        return view_func(request, *args, **kwargs)
    return wrapper

def company_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('company_id'):
            return redirect('/company/login/')
        return view_func(request, *args, **kwargs)
    return wrapper