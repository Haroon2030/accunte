from django.contrib import admin

from .models import PaymentApproval, PaymentExecutionRecord, PaymentProposal, ProposalAttachment

admin.site.register([PaymentProposal, PaymentApproval, PaymentExecutionRecord, ProposalAttachment])
