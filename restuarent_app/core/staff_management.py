# views/staff_management.py
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth import get_user_model
from core.models import Staff
from core.forms import StaffForm

User = get_user_model()

class StaffListView(ListView):
    model = Staff
    template_name = 'staff/staff_list.html'
    context_object_name = 'staff_list'

class StaffCreateView(CreateView):
    model = Staff
    form_class = StaffForm
    template_name = 'staff/staff_form.html'
    success_url = reverse_lazy('staff_list')

    def form_valid(self, form):
        staff = form.save(commit=False)
        if staff.has_software_access and not staff.user:
            username = self.request.POST.get('username')
            password = self.request.POST.get('password') or '1122'
            user = User.objects.create_user(username=username, password=password)
            staff.user = user
        staff.save()
        return super().form_valid(form)

class StaffUpdateView(UpdateView):
    model = Staff
    form_class = StaffForm
    template_name = 'staff/staff_form.html'
    success_url = reverse_lazy('staff_list')

    def form_valid(self, form):
        staff = form.save(commit=False)
        if staff.has_software_access and not staff.user:
            username = self.request.POST.get('username')
            password = self.request.POST.get('password') or '1122'
            user = User.objects.create_user(username=username, password=password)
            staff.user = user
        staff.save()
        return super().form_valid(form)

class StaffDeleteView(DeleteView):
    model = Staff
    template_name = 'staff/staff_confirm_delete.html'
    success_url = reverse_lazy('staff_list')