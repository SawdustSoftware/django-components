from django.test import TestCase
from django.test.client import Client
from django.template import Template
from sekizai.context import SekizaiContext
from django_dynamic_fixture import G
from django.conf import settings

from jobboard.models import Review
from member.models import Badge
from attribute.models import Attribute




class TemplateTagsTestCase(TestCase):

    def setUp(self):
        self.client = Client(HTTP_HOST = "django.testserver")
        self.badge = G(Badge, filename="secure")
        self.attrs = [G(Attribute, slug=q[0]) for q in settings.ATTR_QUESTIONS]

    def make_random_hash(self):
        import random
        return str(random.getrandbits(128))

    def test_add_review(self):

        reviewtext = self.make_random_hash()
        reviewtext2 = self.make_random_hash()

        #test 1 review
        review = G(Review, status=Review.STATUS.active)
        subscriber = review.subscriber
        review.comment = reviewtext
        review.save()

        t = Template('{% load components_maker %}{% reviewscomponent subscriber 5 %}')
        c = SekizaiContext({"subscriber": subscriber})
        html = t.render(c)
        self.assertIn(reviewtext, html)

        #add another review to same subscriber
        review2 = G(Review, status=Review.STATUS.active)
        review2.comment = reviewtext2
        review2.subscriber = subscriber
        review2.save()

        t2 = Template('{% load components_maker %}{% reviewscomponent subscriber 5 %}')
        c2 = SekizaiContext({"subscriber": subscriber})
        html2 = t2.render(c2)
        self.assertIn(reviewtext, html2)
        self.assertIn(reviewtext2, html2)

    def test_change_profile(self):
        reviewtext = self.make_random_hash()

        #add 1 review
        review = G(Review, status=Review.STATUS.active)
        subscriber = review.subscriber
        review.comment = reviewtext
        review.save()

        subscriber.vanity_url = "puppies"
        subscriber.save()

        t = Template('{% load components_maker %}{% reviewscomponent subscriber 5 %}')
        c = SekizaiContext({"subscriber": subscriber})
        html = t.render(c)
        self.assertIn(reviewtext, html)

        #get old cache key
        from member.util import get_template_cache_key
        print get_template_cache_key("maker_profile", [subscriber, 1])
        print get_template_cache_key("maker_profile", [subscriber.id, 1])
        from components.templatetags.components_maker import ReviewsComponent
        print ReviewsComponent.get_cache_key(dict(subscriber=subscriber, size=5))
        print ReviewsComponent.get_cache_key(dict(subscriber=subscriber.id, size=5))


        #now change profile description
        desc_hash = self.make_random_hash()
        subscriber.description = subscriber.description + desc_hash

        #now test reviews again
        c2 = SekizaiContext({"subscriber": subscriber})
        html = t.render(c2)
        self.assertIn(reviewtext, html)

        #now test template change
        response = self.client.get("/by/%s/" % subscriber.vanity_url, follow=True)
        print response
        print response.redirect_chain
        self.assertEqual(response.status_code, 200)
        self.assertIn(desc_hash, response.content)
