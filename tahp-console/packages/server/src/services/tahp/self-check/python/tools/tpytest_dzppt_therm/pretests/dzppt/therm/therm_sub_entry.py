from tpytest.scheme.scheme_subprocess_entry import SchemeSubprocessEntry


class ThermSubEntry(SchemeSubprocessEntry):
    option_start_class_path = 'pretests.dzppt.therm.therm_pretest.ThermPretest'


if __name__ == "__main__":
    import asyncio

    asyncio.run(ThermSubEntry.main())
