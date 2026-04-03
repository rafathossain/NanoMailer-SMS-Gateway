def user_profile_context(request):
    """
    Context processor to add user profile data to all templates.
    """
    context = {
        'user_balance': 0.00,
        'user_full_name': 'Guest',
        'user_email': None,
        'user_photo': None,
    }
    
    if request.user.is_authenticated:
        # Get user's full name
        context['user_full_name'] = request.user.get_full_name() or request.user.first_name or request.user.username
        # Get user's email
        context['user_email'] = request.user.email
        
        # Get user's profile data
        try:
            if hasattr(request.user, 'profile'):
                context['user_balance'] = request.user.profile.balance
                if request.user.profile.photo:
                    context['user_photo'] = request.user.profile.photo.url
        except Exception:
            context['user_balance'] = 0.00
            context['user_photo'] = None
    
    return context
