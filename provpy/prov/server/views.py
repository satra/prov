import json
from django.contrib.auth import login, authenticate
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template.context import RequestContext
from django.utils.datastructures import MultiValueDictKeyError
from tastypie.models import ApiKey
from guardian.shortcuts import * #assign, remove_perm, get_perms_for_model, get_objects_for_user, get_users_with_perms
from prov.model import ProvBundle
from prov.model.graph import prov_to_dot
from prov.server.forms import ProfileForm
from prov.persistence.models import PDBundle 



def registration(request):
    if(request.user.is_authenticated()):
        return HttpResponseRedirect('/prov/home')
    if request.method == 'POST':
        form = ProfileForm(request.POST)
        if form.is_valid():
            User.objects.create_user(username=form.cleaned_data['username'],
                                            password=form.cleaned_data['password'])
            user = authenticate(username=form.cleaned_data['username'],
                                password=form.cleaned_data['password'])
            login(request,user)
            if form.data['next']:
                return HttpResponseRedirect(form.data['next'])
            return HttpResponseRedirect('/prov/home')
        else:
            return render_to_response('server/register.html',{'form': form, 'next': form.data['next']}, 
                                      context_instance=RequestContext(request))
    form = ProfileForm()
    try:
        next_page = request.GET['next']
    except MultiValueDictKeyError:
        next_page = ''
    return render_to_response('server/register.html', {'form': form, 'next': next_page}, 
                              context_instance=RequestContext(request))
    
@login_required
def profile(request):
        if request.method == 'POST':
            try:
                bundle_id = request.POST['delete_id']
                pdBundle = get_object_or_404(PDBundle, pk=bundle_id)
                if not request.user.has_perm('delete_pdbundle', pdBundle):
                    return render_to_response('server/403.html', {'logged': True}, context_instance=RequestContext(request))
                bundle_id = pdBundle.rec_id
                pdBundle.delete()
                messages.success(request, 'The bundle with ID ' + bundle_id + ' was successfully deleted.')
            except MultiValueDictKeyError:
                prov_bundle = json.loads(request.POST['content'], cls=ProvBundle.JSONDecoder)
                pdbundle = PDBundle.create(request.POST['rec_id'], request.POST['asserter'], request.user)
                pdbundle.save_bundle(prov_bundle)
                messages.success(request, 'The bundle was successfully created with ID ' + `pdbundle.id` + ".")
                assign('view_pdbundle',request.user,pdbundle)
                assign('change_pdbundle',request.user,pdbundle)
                assign('delete_pdbundle',request.user,pdbundle)
                assign('admin_pdbundle',request.user,pdbundle)
                assign('ownership_pdbundle',request.user,pdbundle)
                
        perms = get_perms_for_model(PDBundle)
        l_perm = []
        for i in range(len(perms)):
            l_perm.append(perms[i].codename)
        
        return render_to_response('server/profile.html', 
                                  {'bundles': get_objects_for_user
                                   (user=request.user, 
                                    perms = l_perm, klass=PDBundle, any_perm=True).order_by('id'),
                                   'logged': True },
                                  context_instance=RequestContext(request))

@login_required
def bundle_detail(request, bundle_id):
    pdBundle = get_object_or_404(PDBundle, pk=bundle_id)
    if not request.user.has_perm('view_pdbundle', pdBundle):
        return render_to_response('server/403.html', {'logged': True}, context_instance=RequestContext(request))
    prov_g = pdBundle.get_prov_bundle() 
    prov_n = prov_g.get_provn()
    prov_json = json.dumps(prov_g, indent=4, cls=ProvBundle.JSONEncoder) 
    return render_to_response('server/detail.html',
                              {'logged': True, 'bundle': pdBundle, 'prov_n': prov_n, 'prov_json': prov_json},
                              context_instance=RequestContext(request))
    
def bundle_svg(request, bundle_id):
    pdBundle = get_object_or_404(PDBundle, pk=bundle_id)
    if not request.user.has_perm('view_pdbundle', pdBundle):
        return render_to_response('server/403.html', {'logged': True}, context_instance=RequestContext(request))
    prov_g = pdBundle.get_prov_bundle()
    dot = prov_to_dot(prov_g)
    svg_content = dot.create(format='svg')
    return HttpResponse(content=svg_content, mimetype='image/svg+xml')
    
@login_required
def create(request):
    return render_to_response('server/create.html',{'logged': True},
                              context_instance=RequestContext(request))

@login_required
def auth(request):
    key = None
    date = None
    try:
        api_key = ApiKey.objects.get(user=request.user)
    except ApiKey.DoesNotExist:
        api_key = None
    
    if request.method == 'POST':
        try:
            action = request.POST['action']
            if action == 'delete' and api_key:
                api_key.delete()
                api_key = None
                messages.success(request, 'The API key was successfully deleted.')
            elif action == 'generate':
                if not api_key:
                    api_key = ApiKey.objects.create(user=request.user)
                else:
                    api_key.key = ApiKey.generate_key(api_key)
                messages.success(request, 'The API key was successfully generated.')
        except MultiValueDictKeyError:
            pass

    if api_key:
        key = api_key.key
        date = api_key.created
        
    return render_to_response('server/auth.html',{'logged': True, 'key': key, 'date': date,},
                              context_instance=RequestContext(request))

@login_required
def auth_help(request):
    return render_to_response('server/auth_help.html',{'logged': True})

def _update_perms(target, role, pdBundle):
        perms = get_perms_for_model(PDBundle)
        l_perm = []
        for i in range(len(perms)):
            l_perm.append(perms[i].codename)
        for permission in l_perm:
                remove_perm(permission, target, pdBundle)
        if role == 'none':
            return
        assign('view_pdbundle', target, pdBundle)
        if role == 'Reader':
            return
        assign('change_pdbundle', target, pdBundle)
        if role == 'Contributor':
            return
        assign('delete_pdbundle', target, pdBundle)
        if role == 'Editor':
            return
        assign('admin_pdbundle', target, pdBundle)
            
@login_required
def admin_bundle(request, bundle_id):
    pdBundle = get_object_or_404(PDBundle, pk=bundle_id)
    if not request.user.has_perm('admin_pdbundle', pdBundle):
        return render_to_response('server/403.html', {'logged': True}, context_instance=RequestContext(request))
    if request.method == 'POST':
        try:
            name = request.POST['name']
            role = request.POST['role']
            type = request.POST['type']
            if role not in ('none','Reader','Contributor','Editor','Administrator'):
                raise Exception
            if type == 'user':
                target = User.objects.get(username=name)
                _update_perms(target, role, pdBundle)
            elif type == 'group':
                target = Group.objects.get(name=name)
                _update_perms(target, role, pdBundle)
        except User.DoesNotExist:
            messages.error(request, 'User does not exist!')
        except Group.DoesNotExist:
            messages.error(request, 'Group does not exist!')
        except Exception:
            pass

    initial_list = get_users_with_perms(pdBundle, attach_perms = True, with_group_users=False)
    users={}
    for user in initial_list:
        users[user] = len(initial_list[user])
    initial_list = get_groups_with_perms(pdBundle, attach_perms=True)
    public = False
    groups={}
    for group in initial_list:
        groups[group] = len(initial_list[group])
        if group.name == 'public':
            public = True
    all_users=[]
    for user in User.objects.all():
        if user.id != -1:
            all_users.append(user.username)
    all_users.sort()
    all_groups=[]
    for group in Group.objects.all():
        if group.name != 'public':
            all_groups.append(group.username)
    all_groups.sort()    
    return render_to_response('server/admin.html',
                              {'logged': True, 'bundle': pdBundle, 'public': public,
                               'users': users, 'groups': groups,
                               'all_users': all_users, 'all_groups': all_groups},
                              context_instance=RequestContext(request))