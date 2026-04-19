"""
النظام الأساسي - API Views
"""
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import Permission, Role, UserProfile
from .serializers import (
    PermissionSerializer, 
    RoleSerializer, 
    RoleListSerializer,
    UserSerializer,
    UserProfileSerializer
)

User = get_user_model()


class PermissionViewSet(viewsets.ModelViewSet):
    """ViewSet للصلاحيات"""
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['module', 'is_active']
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'module', 'created_at']
    ordering = ['module', 'name']
    
    @action(detail=False, methods=['get'])
    def by_module(self, request):
        """الحصول على الصلاحيات مجمعة حسب الوحدة"""
        modules = {}
        for perm in self.get_queryset().filter(is_active=True):
            module = perm.module
            if module not in modules:
                modules[module] = {
                    'module': module,
                    'module_display': perm.get_module_display(),
                    'permissions': []
                }
            modules[module]['permissions'].append(PermissionSerializer(perm).data)
        return Response(list(modules.values()))


class RoleViewSet(viewsets.ModelViewSet):
    """ViewSet للأدوار"""
    queryset = Role.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return RoleListSerializer
        return RoleSerializer
    
    @action(detail=True, methods=['post'])
    def assign_permissions(self, request, pk=None):
        """تعيين صلاحيات للدور"""
        role = self.get_object()
        permission_ids = request.data.get('permission_ids', [])
        permissions = Permission.objects.filter(id__in=permission_ids)
        role.permissions.set(permissions)
        return Response(RoleSerializer(role).data)
    
    @action(detail=True, methods=['post'])
    def add_permission(self, request, pk=None):
        """إضافة صلاحية للدور"""
        role = self.get_object()
        permission_id = request.data.get('permission_id')
        try:
            permission = Permission.objects.get(id=permission_id)
            role.permissions.add(permission)
            return Response(RoleSerializer(role).data)
        except Permission.DoesNotExist:
            return Response(
                {'error': 'الصلاحية غير موجودة'}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'])
    def remove_permission(self, request, pk=None):
        """إزالة صلاحية من الدور"""
        role = self.get_object()
        permission_id = request.data.get('permission_id')
        try:
            permission = Permission.objects.get(id=permission_id)
            role.permissions.remove(permission)
            return Response(RoleSerializer(role).data)
        except Permission.DoesNotExist:
            return Response(
                {'error': 'الصلاحية غير موجودة'}, 
                status=status.HTTP_404_NOT_FOUND
            )


class UserViewSet(viewsets.ModelViewSet):
    """ViewSet للمستخدمين"""
    queryset = User.objects.select_related('profile', 'profile__role', 'profile__branch').all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'is_staff', 'is_superuser']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'date_joined', 'last_login']
    ordering = ['username']
    
    @action(detail=False, methods=['get'])
    def roles(self, request):
        """الحصول على قائمة الأدوار المتاحة"""
        roles = Role.objects.filter(is_active=True)
        return Response(RoleListSerializer(roles, many=True).data)
    
    @action(detail=True, methods=['post'])
    def assign_role(self, request, pk=None):
        """تعيين دور للمستخدم"""
        user = self.get_object()
        role_id = request.data.get('role_id')
        branch_id = request.data.get('branch_id')
        profile, _ = UserProfile.objects.get_or_create(user=user)
        
        if role_id:
            try:
                role = Role.objects.get(id=role_id)
                profile.role = role
            except Role.DoesNotExist:
                return Response(
                    {'error': 'الدور غير موجود'}, 
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            profile.role = None
        
        if branch_id:
            from apps.branches.models import Branch
            try:
                branch = Branch.objects.get(id=branch_id)
                profile.branch = branch
            except Branch.DoesNotExist:
                return Response(
                    {'error': 'الفرع غير موجود'}, 
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            profile.branch = None
        
        profile.save()
        return Response(UserSerializer(user).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
    """الحصول على معلومات المستخدم الحالي"""
    user = request.user
    
    # Get profile info
    profile_data = {}
    if hasattr(user, 'profile'):
        profile = user.profile
        profile_data = {
            'role': profile.role.id if profile.role else None,
            'role_name': profile.role.name if profile.role else None,
            'role_type': profile.role.role_type if profile.role else None,
            'branch': profile.branch.id if profile.branch else None,
            'branch_name': profile.branch.name if profile.branch else None,
            'can_see_all_branches': profile.can_see_all_branches,
        }
    
    return Response({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': user.get_full_name() or user.username,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'permissions': list(user.get_all_permissions()),
        **profile_data
    })


def admin_frontend(request, **kwargs):
    """عرض واجهة React"""
    return render(request, 'admin/frontend.html')
