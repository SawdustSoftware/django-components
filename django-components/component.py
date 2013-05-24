from django.core.cache import cache
from django import template
from django.template import loader, Context
from django.utils.hashcompat import md5_constructor

from classytags.core import Tag, Options
from classytags.arguments import KeywordArgument


from sekizai.helpers import get_varname
from sekizai.context import SekizaiContext
def sekizai_add_to_block(context, block, value):
    """Sekizai has no python API yet so gotta hack it."""
    context[get_varname()][block].append(value)




class SimpleKeywordArgument(KeywordArgument):

    def __init__(self, name, default=None, required=True, resolve=True,
                 defaultkey=None, splitter='='):
        super(KeywordArgument, self).__init__(name, default, required, resolve)
        self.defaultkey = name
        self.splitter = splitter

    def parse(self, parser, token, tagname, kwargs):
        if self.name in kwargs:  # pragma: no cover
            return False
        else:
            key, value = self.parse_token(parser, token)
            kwargs[self.key] = value
            return True

class ComponentMetaclass(type):

    CACHED          = True
    CACHE_DURATION  = 60 * 60 * 24


    def __new__(meta, name, parents, attrs):

        if not [b for b in parents if isinstance(b, ComponentMetaclass)]:
            return super(ComponentMetaclass, meta).__new__(meta, name, parents, attrs)

        if not attrs.get("name", None):
            attrs["name"] = name.lower()
        if not attrs.get("cache_prefix", None):
            attrs["cache_prefix"] = "component::%s" % attrs["name"]
        if not attrs.get("sekizai_blocks", None):
            attrs["sekizai_blocks"] = None

        if not attrs.get("cached", None):
            attrs["cached"] = ComponentMetaclass.CACHED
        if not attrs.get("cache_duration", None):
            attrs["cache_duration"] = ComponentMetaclass.CACHE_DURATION

        if not attrs.get("template_name", None):
            raise ValueError("You must define a template_name in your component class.")

        #infer cache vary params from options
        opts = attrs["options"]
        if not attrs.get("cache_vary_on", None):
            attrs["cache_vary_on"] = opts.all_argument_names

        #add in generic cache options for runtime
        component_options = Options(
            KeywordArgument("cached",
                            defaultkey="cached",
                            default=attrs["cached"],
                            required=False),
            KeywordArgument("cache_duration",
                            defaultkey="cache_duration",
                            default=attrs["cache_duration"],
                            required=False),
        )
        opts.options[None] += component_options.options[None]

        return super(ComponentMetaclass, meta).__new__(meta, name, parents, attrs)



class Component(Tag):
    """An encapsulated thing that is meant to be reused across the site in many
    different views. Eg: Maker reviews box, little stats widget. It's meant to
    be like a mini-version of a view that you can embed in another page.

    Benefits: easy to reuse code, change things in only one place to change
    them everywhere, cache components automatically, turn caching on and off
    without changing the template. All client side code (js, css, html) for one
    component is in one place. No mucking around with manual cache key
    generating.

    In your template, add:

        {% components_maker %}
        {% reviewscomponent subscriber %}

    Ta da.

    To build a new component, simply inherit Component and:
        - Override fetch_data to return the context for your component template
        - Override options to pass in any variables you need, like user ids.
        This is in Classytags format.
        - Declare name as the template file to use.
        - Optionally override any other (cache key, rendering) function for
        more complex behavior

    Overridables:
        - cached=True: enable / disable cache.
        - cache_duration=60*60*24: cache time in seconds.
        - tag_name=classname.lower(): name of the template tag
        - template_name: Name of the template to use
        - cache_vary_on: List of attribute names to get the value of when
        generating a cache key. Defaults to detecting the template tag
        arguments and using those.
        - sekizai_blocks: Dictionary of blockname -> content to inject js /
        css / etc into the template.

    TODO: maybe have post_render also cache subcontext data
    TODO: look into disabling offline compression to get compression to play
    nice with components/sekizai https://github.com/ojii/django-sekizai/issues/4

    """

    __metaclass__ = type("combometaclass", (type(Tag), ComponentMetaclass), {})

    def __init__(self, *args, **kwargs):

        self.template_tag_args = None
        self.template_tag_kwargs = None
        self.load_template()

        super(Component, self).__init__(*args, **kwargs)

    # ----------------------- Constants ---------------------

    #user argument supplied

    @classmethod
    def get_cache_key(cls, kwargs):
        vary_values = [str(kwargs[var]) for var in cls.cache_vary_on]
        args = md5_constructor(':'.join(vary_values))
        return '%s::%s' % (cls.cache_prefix, args.hexdigest())

    @classmethod
    def clear_cache(cls, **kwargs):
        """To clear a specific cached component, pass this the exact keyword
        arguments that you would pass it in the template. Eg
        ReviewsComponent.clear_cache(subscriber=joe, size=5)."""
        known_args = cls.cache_vary_on
        if set(kwargs.keys()) != set(known_args):
            raise ValueError("Did you pass in the wrong arguments? You passed\
                             %s, we have %s. You might need to pass in inferred\
                             default values too." % (kwargs, known_args))
        return cache.delete(cls.get_cache_key(kwargs))

    # -------------------- Custom CSS / js ---------------------

    def add_blocks(self, context):
        """Add something to a sekizai block, like custom css or js for this component."""
        if self.sekizai_blocks:
            for block, value in self.sekizai_blocks.items():
                sekizai_add_to_block(context, block, value)

    # ----------------------- Caching ---------------------

    def load_from_cache(self):
        return cache.get(self.cache_key)

    def save_to_cache(self, data):
        return cache.set(self.cache_key, data, self.cache_duration)

    # ----------------------- Rendering ---------------------

    @staticmethod
    def merge_contexts(context, sub_context):
        """Utility function to call in post_render to merge the global context
        with the context of the component."""
        return context.update(sub_context)

    @staticmethod
    def merge_sekizai_data(context, sub_context):
        """Utility function to call in post_render to merge the sekizai data in
        the component context into the global context."""
        varname = get_varname()
        for sub_block, sub_values in sub_context[varname].items():
            for item in sub_values:
                if item not in context[varname][sub_block]:
                    context[varname][sub_block].append(item)

    def post_render(self, context, sub_context, rendered_data):
        """Hook this to do something after the render is done. This is
        important because some context stuff gets changed during the render
        process. So if you want to pass stuff to the upper context, or modify
        the output to the rendered data, do it here. This doesn't run if a
        cached version is served."""
        return rendered_data

    def load_template(self):
        if not self.template_name:
            raise ValueError("Component %s doesn't have a template, try setting template in it?" % self.name)
        self._template = loader.get_template(self.template_name)

    def render_template(self, sub_context):
        """Render the model data into html."""
        return self._template.render(sub_context)

    def render_tag(self, context, *args, **kwargs):
        """Return the result from cache or fresh."""

        self.template_tag_args = args
        self.template_tag_kwargs = kwargs
        self.cache_key = self.get_cache_key(self.template_tag_kwargs)
        self.add_blocks(context)

        if not self.cached:
            sub_context = SekizaiContext(self.fetch_data(context))
            rendered_data = self.render_template()
            rendered_data = self.post_render(context, sub_context, rendered_data)
            return rendered_data

        cached_data = self.load_from_cache()
        if cached_data:
            return cached_data
        else:
            sub_context = SekizaiContext(self.fetch_data(context))
            rendered_data = self.render_template(sub_context)
            rendered_data = self.post_render(context, sub_context, rendered_data)
            self.save_to_cache(rendered_data)
            return rendered_data

    # --------------------- Override These ---------------------
    def fetch_data(self, context):
        """Do whatever to fetch data for the context for the component
        template. Meant to be overridden. Use self.template_tag_args and
        self.template_tag_kwargs to refer to runtime template tag arguments."""

        return {}

