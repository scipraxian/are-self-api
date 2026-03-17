from rest_framework import routers

from corpus_callosum.api import CorpusCallosumViewSet

V2_CORPUS_CALLOSUM = routers.SimpleRouter()
V2_CORPUS_CALLOSUM.register(
    r'corpus_callosum', CorpusCallosumViewSet, basename='corpuscallosum'
)
