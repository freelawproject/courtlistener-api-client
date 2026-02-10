from courtlistener.models.endpoint import Endpoint
from courtlistener.models.endpoints.aba_ratings import AbaRatingsEndpoint
from courtlistener.models.endpoints.agreements import AgreementsEndpoint
from courtlistener.models.endpoints.alerts import AlertsEndpoint
from courtlistener.models.endpoints.attorneys import AttorneysEndpoint
from courtlistener.models.endpoints.audio import AudioEndpoint
from courtlistener.models.endpoints.bankruptcy_information import (
    BankruptcyInformationEndpoint,
)
from courtlistener.models.endpoints.clusters import ClustersEndpoint
from courtlistener.models.endpoints.courts import CourtsEndpoint
from courtlistener.models.endpoints.debts import DebtsEndpoint
from courtlistener.models.endpoints.disclosure_positions import (
    DisclosurePositionsEndpoint,
)
from courtlistener.models.endpoints.disclosure_typeahead import (
    DisclosureTypeaheadEndpoint,
)
from courtlistener.models.endpoints.docket_alerts import DocketAlertsEndpoint
from courtlistener.models.endpoints.docket_entries import DocketEntriesEndpoint
from courtlistener.models.endpoints.docket_tags import DocketTagsEndpoint
from courtlistener.models.endpoints.dockets import DocketsEndpoint
from courtlistener.models.endpoints.educations import EducationsEndpoint
from courtlistener.models.endpoints.financial_disclosures import (
    FinancialDisclosuresEndpoint,
)
from courtlistener.models.endpoints.fjc_integrated_database import (
    FjcIntegratedDatabaseEndpoint,
)
from courtlistener.models.endpoints.gifts import GiftsEndpoint
from courtlistener.models.endpoints.increment_event import (
    IncrementEventEndpoint,
)
from courtlistener.models.endpoints.investments import InvestmentsEndpoint
from courtlistener.models.endpoints.non_investment_incomes import (
    NonInvestmentIncomesEndpoint,
)
from courtlistener.models.endpoints.opinions import OpinionsEndpoint
from courtlistener.models.endpoints.opinions_cited import OpinionsCitedEndpoint
from courtlistener.models.endpoints.originating_court_information import (
    OriginatingCourtInformationEndpoint,
)
from courtlistener.models.endpoints.parties import PartiesEndpoint
from courtlistener.models.endpoints.people import PeopleEndpoint
from courtlistener.models.endpoints.political_affiliations import (
    PoliticalAffiliationsEndpoint,
)
from courtlistener.models.endpoints.positions import PositionsEndpoint
from courtlistener.models.endpoints.prayers import PrayersEndpoint
from courtlistener.models.endpoints.recap_documents import (
    RecapDocumentsEndpoint,
)
from courtlistener.models.endpoints.recap_fetch import RecapFetchEndpoint
from courtlistener.models.endpoints.recap_query import RecapQueryEndpoint
from courtlistener.models.endpoints.reimbursements import (
    ReimbursementsEndpoint,
)
from courtlistener.models.endpoints.retention_events import (
    RetentionEventsEndpoint,
)
from courtlistener.models.endpoints.schools import SchoolsEndpoint
from courtlistener.models.endpoints.search import SearchEndpoint
from courtlistener.models.endpoints.sources import SourcesEndpoint
from courtlistener.models.endpoints.spouse_incomes import SpouseIncomesEndpoint
from courtlistener.models.endpoints.tag import TagEndpoint
from courtlistener.models.endpoints.tags import TagsEndpoint
from courtlistener.models.endpoints.visualizations import (
    VisualizationsEndpoint,
)
from courtlistener.models.endpoints.visualizations_json import (
    VisualizationsJsonEndpoint,
)

__all__ = [
    "SearchEndpoint",
    "DocketsEndpoint",
    "BankruptcyInformationEndpoint",
    "OriginatingCourtInformationEndpoint",
    "DocketEntriesEndpoint",
    "RecapDocumentsEndpoint",
    "CourtsEndpoint",
    "AudioEndpoint",
    "ClustersEndpoint",
    "OpinionsEndpoint",
    "OpinionsCitedEndpoint",
    "TagEndpoint",
    "PeopleEndpoint",
    "DisclosureTypeaheadEndpoint",
    "PositionsEndpoint",
    "RetentionEventsEndpoint",
    "EducationsEndpoint",
    "SchoolsEndpoint",
    "PoliticalAffiliationsEndpoint",
    "SourcesEndpoint",
    "AbaRatingsEndpoint",
    "PartiesEndpoint",
    "AttorneysEndpoint",
    "RecapFetchEndpoint",
    "RecapQueryEndpoint",
    "FjcIntegratedDatabaseEndpoint",
    "TagsEndpoint",
    "DocketTagsEndpoint",
    "PrayersEndpoint",
    "IncrementEventEndpoint",
    "VisualizationsJsonEndpoint",
    "VisualizationsEndpoint",
    "AgreementsEndpoint",
    "DebtsEndpoint",
    "FinancialDisclosuresEndpoint",
    "GiftsEndpoint",
    "InvestmentsEndpoint",
    "NonInvestmentIncomesEndpoint",
    "DisclosurePositionsEndpoint",
    "ReimbursementsEndpoint",
    "SpouseIncomesEndpoint",
    "AlertsEndpoint",
    "DocketAlertsEndpoint",
]

ENDPOINTS: dict[str, type[Endpoint]] = {
    "search": SearchEndpoint,
    "dockets": DocketsEndpoint,
    "bankruptcy_information": BankruptcyInformationEndpoint,
    "originating_court_information": OriginatingCourtInformationEndpoint,
    "docket_entries": DocketEntriesEndpoint,
    "recap_documents": RecapDocumentsEndpoint,
    "courts": CourtsEndpoint,
    "audio": AudioEndpoint,
    "clusters": ClustersEndpoint,
    "opinions": OpinionsEndpoint,
    "opinions_cited": OpinionsCitedEndpoint,
    "tag": TagEndpoint,
    "people": PeopleEndpoint,
    "disclosure_typeahead": DisclosureTypeaheadEndpoint,
    "positions": PositionsEndpoint,
    "retention_events": RetentionEventsEndpoint,
    "educations": EducationsEndpoint,
    "schools": SchoolsEndpoint,
    "political_affiliations": PoliticalAffiliationsEndpoint,
    "sources": SourcesEndpoint,
    "aba_ratings": AbaRatingsEndpoint,
    "parties": PartiesEndpoint,
    "attorneys": AttorneysEndpoint,
    "recap_fetch": RecapFetchEndpoint,
    "recap_query": RecapQueryEndpoint,
    "fjc_integrated_database": FjcIntegratedDatabaseEndpoint,
    "tags": TagsEndpoint,
    "docket_tags": DocketTagsEndpoint,
    "prayers": PrayersEndpoint,
    "increment_event": IncrementEventEndpoint,
    "visualizations_json": VisualizationsJsonEndpoint,
    "visualizations": VisualizationsEndpoint,
    "agreements": AgreementsEndpoint,
    "debts": DebtsEndpoint,
    "financial_disclosures": FinancialDisclosuresEndpoint,
    "gifts": GiftsEndpoint,
    "investments": InvestmentsEndpoint,
    "non_investment_incomes": NonInvestmentIncomesEndpoint,
    "disclosure_positions": DisclosurePositionsEndpoint,
    "reimbursements": ReimbursementsEndpoint,
    "spouse_incomes": SpouseIncomesEndpoint,
    "alerts": AlertsEndpoint,
    "docket_alerts": DocketAlertsEndpoint,
}
