from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import ListView, CreateView, DeleteView
from django.views import View
from django.urls import reverse_lazy
from .models import Payment
from .forms import PaymentForm
from accounts.mixins import TreasurerRequiredMixin, AdminRequiredMixin, MemberAccessMixin, AdminPasswordDeleteMixin
from utils.exports import export_csv, export_pdf


class PaymentListView(MemberAccessMixin, ListView):
    model = Payment
    template_name = 'payments/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 20

    def get_queryset(self):
        qs = Payment.objects.select_related('member', 'loan__member')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(member__name__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class PaymentCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = 'payments/payment_form.html'
    success_url = reverse_lazy('payments:list')
    success_message = "Payment recorded. Loan balance updated."

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['loan_id'] = self.request.GET.get('loan')
        return kwargs

    def form_valid(self, form):
        form.instance.member = form.cleaned_data['loan'].member
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        loan_id = self.request.GET.get('loan')
        if loan_id:
            from loans.models import Loan
            try:
                ctx['prefilled_loan'] = Loan.objects.get(pk=loan_id)
            except Loan.DoesNotExist:
                pass
        return ctx


class PaymentDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = Payment
    template_name = 'payments/payment_confirm_delete.html'
    success_url = reverse_lazy('payments:list')


class PaymentExportView(MemberAccessMixin, View):
    def get(self, request):
        format_type = request.GET.get('format', 'csv')
        qs = Payment.objects.select_related('member', 'loan__member')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(member__name__icontains=q)

        fields = [
            ('member.name', 'Member'),
            ('loan.loan_amount', 'Loan Amount (KES)'),
            ('amount', 'Payment (KES)'),
            (lambda obj: obj.get_payment_type_display(), 'Method'),
            ('mpesa_code', 'M-Pesa Code'),
            ('date', 'Date'),
            ('notes', 'Notes'),
        ]
        if format_type == 'pdf':
            return export_pdf(qs, 'payments', 'Loan Payments Report', fields, orientation='landscape')
        return export_csv(qs, 'payments', fields)
